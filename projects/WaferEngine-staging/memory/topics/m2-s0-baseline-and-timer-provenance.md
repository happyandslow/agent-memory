---
summary: M2-S0 measurement session — the pr14 pdSeparate mtbench8 baseline reproduced bit-identical on real WSE-3 at snapshot a3a509c, the code-derived KV wire payload (32.000 MiB/request, 8/7 layer-envelope factor), and which timing.json fields are safe to quote.
tags: [waferengine-staging, m2, pdseparate, measurement, timing, bandwidth, cs3-cluster, provenance]
---

# M2-S0 — pr14 pdSeparate baseline + `timing.json` provenance

Session 2026-07-28. Snapshot **`a3a509c`**, branch `lexu/staging/m2-benchmark`, worktree
`/home/lexu/we-m2bench`. Real WSE-3 on EPCC CS-3, real Qwen3-1.7B weights, **zero source
changes**.

> **Plan and state live in the durable docs, which win on any conflict:**
> `milestones/M2-tiering-cost-model.md` (anchors, Verification log, subtasks) and
> `milestones/M2-timer-provenance.md` (the full per-field table). This file keeps only the
> incidental learnings — the things that would be re-discovered the hard way otherwise.
> Related: [[pr14-real-serving-port-contract]], [[prefill-decode-transfer-bandwidth]],
> [[h2d-host-device-bandwidth]], [[e2e-pdSeparate-device-validation]].

## The reusable technique: prove same-source before comparing timings

`device_verdict.json` carries a **`trace_sha256`** covering all 8 requests' prompt ids,
prefill top-k value bits/ids, and decode sampled ids. Comparing that single hash against the
reference run proves every divisor is identical, so any timing delta is timing and nothing
else. Both our runs matched
`004463a841608f68f7032631703ba1c88ebb3770e247cadf1880441c23930538`, with
`request_signatures` 8/8.

Two gotchas around this:

- **`launch.py` never reads `golden_token_ids_*.json`.** The checked-in golden file looks
  like a gate but nothing enforces it; `device_verdict.json`'s own checks are structural
  only (round counts, trace-hash presence). Token-level reproducibility must be compared by
  hand — or, far more cheaply, via `trace_sha256`.
- **`results.json` holds no token ids**, only counts and decoded text. Ids live in
  `device_trace.npz` as `request_<i>_decode_sampled_ids`, with the `-2` HOST_STOP sentinel
  still in the array (filter it, as `launch.py:336-337` does).

## What is deterministic and what is not

Of 242 leaf fields in `timing.json`, **every device-side field reproduced to ≤0.02%; all
deviation was host-side.** That split is the practical takeaway: the wafer is a stable
measuring instrument, the host is not.

| quantity | reference | ours (n=2) |
|---|---|---|
| decode steady `agg_steady.device_us_per_tok` | 654.954 µs | 654.954 / 655.095 |
| prefill device span | 56912.71 µs | 56912.71 / 56910.73 |
| `per_req_kv_egress_ms` | 23.528 ms | 23.491 / 23.559 |
| `kv_bridge_per_prompt_s` | 0.72 s | **0.058 / 0.059** |
| `per_round_kv_repack_ms` | 29.47 ms | 35.10 / 40.57 (noisiest field in the file) |

## KV wire payload — derive it, never assume it

From `launch_prefill.py:1599-1607`, resolved against `serve_2x4_8k20k.json`:

```
egress bytes = 4 streams · 4 B · P_BLOCK_SIZE(256) · ceil(L/256) · kv_seg_len(8192)
             = 32.000 MiB · ceil(L / 256)          = 33,554,432 B for any L ≤ 256
ingress      = the same, plus 2 MiB of metadata (1 u32 per row×column cell)
```

⇒ measured **1.426 GB/s aggregate, 0.357 GB/s per stream**; useful-KV goodput only
**0.146 GB/s** on 30-token prompts.

Two factors inflate the wire over `B_tok = 112 KB/token`:

- **`8/7`, permanent.** `distribute_layers(28, 8) = [2,4,4,4,4,4,4,2]`, but every PE emits at
  `max_layers_per_block = 4`, so 32 layer slots carry 28 real layers. Applies at every `L`.
  Any `R*`-style formula using `B_tok` understates transport cost by 14%.
- **`256/L`, config artifact.** `CHUNK_SIZE = 256`, so a 30-token prompt still ships a full
  chunk. Vanishes at `L ≥ 256`. It also means `mtbench8`'s egress time is a **floor**, not a
  rate.

**Neither direction zero-extends fp16 into u32** — both pack 2 fp16 per u32
(`launch_prefill.py:794-796`, `launch_decode.py:212`). The "wastes half the wire" property
belongs to the *staging* line only; do not attribute it to pr14.

## Traps in `timing.json` worth remembering

- **The device TSC buffer is loop-carried.** Everything in `tsc.*` *outside* `per_round[]`
  describes the **last round only** while reading like an aggregate — 3.4% on the headline
  `tok_per_s`. Quote `agg_steady.*` and `per_round[].device_steady_*`.
- **`per_round_kv_send_ms = 0.062` is an enqueue**, not wire time (`nonblock=True`, no
  `task_wait`). The arithmetic proves it: 35.7 MB in 0.062 ms would be 575 GB/s. Real
  ingress cost hides in `per_round_recv_first_ms`, mixed with injection and the first forward.
- **Phase wall clocks bracket artifact load.** ~416 s of the reference run's 734 s total is
  measured by *no field at all* (interpreter start, artifact `copytree`, `attach`).
- **`compile_s = 0.0` on a reload is hardcoded, not measured** (`launch_prefill.py:1865`).
- **`kv_bridge_per_prompt_s` and `per_round[].kv_handoff_s` are two different stages**, not a
  whole and its part. The bridge is the orchestrator's npz round trip (`launch.py:284-298`);
  the handoff is decode's own reload + repack (`launch_decode.py:2526-2556`). The 69.5 ms /
  29.5 ms components belong to the second.

## Operational notes for the next device session

- **`--mode reload` is source-fingerprint gated** (`build_manifest.json` vs the current tree).
  A store from a different snapshot is *refused*, not silently served — so the snapshot lock
  is enforced by the tool. Corollary: any kernel edit forces a full recompile.
- **Build cost, as-built:** prefill **419.6 s**, decode **61.6 s** device compile; ~40 min
  end-to-end for both phases including 4 GB weight staging (twice) and ~6.3 GB artifact
  return. Store is 6.3 GB compressed (~23–28 GB raw per phase before zstd).
- **A two-phase build works and is safer than `--build-phase both`:** each phase only
  replaces its own store subdir, and `build_manifest.json` is written *only* when both exist,
  so a half-built store correctly fails the reload gate.
- **`--build-phase decode` re-uploads the full 4 GB of weights.** Budget for it.
- **HF snapshots on CS-3 may lack tokenizer files.** `_install_tokenizer` hard-fails without
  `tokenizer.json`. Check before starting a build; the small files are ~15 MB to upload, and
  symlinking the safetensors avoids duplicating 3.8 GB.
- **`KV_NPZ_DIR` is implemented but unused** (`launch.py:96-107`) — an absolute
  `/dev/shm/<run>` moves the whole P→D npz handoff to tmpfs. The cheapest route to the
  physical floor of the host round trip.
