---
summary: M2-S0 measurement session — the pr14 pdSeparate mtbench8 baseline reproduced bit-identical on real WSE-3 at snapshot a3a509c, what mtbench8's workload shape can and cannot measure, the code-derived KV wire payload (32.000 MiB/request, 8/7 layer-envelope factor), which timing.json fields are safe to quote, and the provenance failures (prose divisor, over-wide wall clock, wrong regression x-axis) that put wrong numbers into durable docs.
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

## Reaching for `mtbench8` as the vehicle for a reuse experiment

It is the obvious candidate — a shipped request set with recorded timings and a golden-token
reference, sitting right next to the model. Read `request_config/mtbench8/prompts.json` before
reusing it, because its shape does not match its name.

`prompts.json` is a **flat list of 8 independent single-turn prompts** — MT-Bench-flavoured
open-ended writing/explanation tasks, no turn structure, no shared system prompt. **The "MT" in
MT-Bench is multi-turn; this config drives it single-turn.** Prompts are 21–36 tokens,
generations 478–3381 tokens: decode-dominated, zero reuse.

Three things it therefore cannot measure:

- **No KV reuse of any kind.** Eight unrelated prompts — nothing to retain, offload, or recompute.
- **Prompts shorter than the transfer quantum.** 21–36 tokens against `CHUNK_SIZE = 256` means
  every prefill ships one full padded chunk, so `per_req_kv_egress_ms` is a **floor**, not a
  length-proportional measurement — no bandwidth-vs-length curve can come out of it, and any
  bandwidth derived from it inherits the padding assumption.
- **It cannot separate re-prefill / force-decode / offload.** At `L_prompt ≈ 30` all three are
  fixed-cost-dominated (re-prefill pays the ~57 ms floor, force-decode ~30 tokens, offload one
  padded chunk). The crossings that matter live at `L` in the thousands.

What it *is* good for is exactly the role it already plays here: baseline reproduction — recorded
timings, a golden-token reference, and the 8/8 bit-identical device validation the frozen `io_loc`
pins cite as their justification. Keep it for that; do not stretch it. Reuse studies need
**fabricated** request sets with controlled shared-prefix fractions and explicit turn structure;
ground the sharing ratios in published traces rather than inventing them (Mooncake carries
`hash_ids`, so exact prefix-sharing percentages are computable — see [[agentic-kv-trace-datasets]]).

General shape worth carrying: compare prompt length against **every** quantization in the path
(chunk size, block size, page size). A workload below the quantum measures the floor, not the slope.
`[unverified]` whether all eight prompts are verbatim MT-Bench items — the conclusion rests on shape,
not provenance.

## Two ways an inherited number reached a decision rule without being measured

Both surfaced in the same session, both load-bearing, both caught only by opening the artifact that
produced the number rather than the number itself.

**The divisor came from prose, not a timer.** `ROADMAP.md`, `GOALS.md §8`, `PROGRESS.md` and
[[kv-cache-policy-tradeoffs]] all carried **"host KV transport as-built ~15 MB/s"**, and the whole
`R* = Δ·BW/B_tok` breakeven used it as `BW`. It is `29.4 MB ÷ "~2 s"`: the numerator is real
(derived from a device-run wavelet count), **the denominator is a `STATUS.md` prose phrase — "a few
seconds"**. The topic file hedged it in its own text as *"measured-ish"*, and every citing doc
silently dropped the hedge. It also describes the wrong branch — the *staging* single-stream colmux
path, which additionally zero-extends fp16 into u32 and wastes half the wire. The pr14 line has been
4-stream varlen for some time and its `per_req_kv_egress_ms` **is** true wire time (a blocking
`task_wait` after four `nonblock` receives), giving **~1.4 GB/s — about 90× higher**. Consequences:
`R*` moves from a degenerate ~0.036 ("always keep KV in place", i.e. no boundary at all) to **≈3**, a
real boundary with requests on both sides; and M4's completion gate ("beat as-built ~15 MB/s") had
**already been cleared by ~90× before it was written**. Note the asymmetry in danger: *a degenerate
`R*` does not look broken — it looks like a strong conclusion.*

**The wall clock spanned more than the quantity being computed.** From the same recorded
`timing.json`, dividing `decode_phase_wall_s = 293.694` by 10,571 generated tokens gives 27.8
ms/token — ~58× the known device rate, apparently "decode is 98% host overhead", which would have
invalidated the entire on-wafer optimization thesis. Wrong: `decode_phase_wall_s` **brackets
`compile_s` (94.5 s), `load_s` (105.3 s) and eight KV handoffs**, and the same file already carries
the steady-state figures (device 655 µs/token, host-observed 740, `host_device_ratio = 1.129` — host
adds ~12%). One file read, before the alarm reached a durable doc.

The operating rules that follow: open the producing artifact before using an inherited number as a
model input, and if you cannot, label it *derived*, not *measured*; carry the original author's
hedge forward, since dropping "measured-ish" during a citation is exactly how a guess becomes a
constant; name the start and end line for any wall clock (`*_phase_wall_s`-style names almost always
include setup); and record per parameter whether it is a **physical floor** or an **as-built
artifact**, or the cost model just re-derives "the current implementation has bugs" for every option.

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

## Per-request breakdown, and the finding hiding in it

| req | prompt tok | generated tok | prefill span | prefill tok/s | decode µs/tok | decode tok/s (device) | decode tok/s (host) |
|---|---|---|---|---|---|---|---|
| 0 | 30 | 1728 | 56.91 ms | 527.1 | 652.25 | 1533.1 | 1357.4 |
| 1 | 25 | 665 | 56.91 ms | 439.3 | 636.72 | 1570.6 | 1392.0 |
| 2 | 36 | 461 | 56.91 ms | 632.6 | 634.57 | 1575.9 | 1397.6 |
| 3 | 21 | 1518 | 56.91 ms | 369.0 | 649.43 | 1539.8 | 1363.5 |
| 4 | 27 | 1714 | 56.91 ms | 474.4 | 651.28 | 1535.4 | 1359.5 |
| 5 | 23 | 509 | 56.91 ms | 404.1 | 636.20 | 1571.8 | 1393.9 |
| 6 | 25 | 3364 | 56.91 ms | 439.3 | 672.81 | 1486.3 | 1315.5 |
| 7 | 21 | 476 | 56.91 ms | 369.0 | 634.69 | 1575.6 | 1397.3 |

**⚠️ The decode spread is not noise — it is context length, and it is linear.** Sort the 8
requests by length and `device_steady_us_per_tok` is **monotonic in all 8**.

**Regress on mean context, not on generated count.** `device_steady_us_per_tok` is an average
over the timed window, and context grows linearly across that window, so an instantaneous cost
`a + b·c` reports as `a + b · mean_ctx` with `mean_ctx = prompt + (warmup_cycles + generated)/2`:

```
cost per token at context c ≈ 627.83 µs + 26.45 ns × c     R² = 0.998
```

⇒ **`654.954 µs/token` is a mean over this workload's generation-length mix** (≈1020 tokens of
context), not a constant. Two extrapolations that are easy to conflate: **one token at 8192
context costs 844 µs**, whereas **a run generating 8192 tokens averages 736 µs/token**.

The independent standalone-decode sweep (479→560 µs across prefill 256→3840, different geometry,
mock weights) implies **≈22.5 ns per context token** — the same quantity, within 15%. Two
unrelated measurements agreeing on the slope is what makes this credible.

> ⚠️ **Correction, same session.** First written as `628.75 µs + 13.22 ns × context`, R² = 0.998,
> monotonic across all 8 requests, and carried into three documents: the fit had been run against
> **generated tokens** while labelled context, and mean context is about half the generated count,
> so the slope was ~2× low. **R² was unchanged by the fix (0.998 either way) — a linear rescale of
> the x-axis leaves R² untouched, so a near-perfect fit is evidence of linearity and says nothing
> about whether the right variable was fitted.** What should have caught it immediately: 13.22 vs
> the standalone sweep's 22.5 is a factor-of-2 gap between two measurements of the *same* quantity,
> and it was written down as "agrees in direction and order of magnitude" instead of being
> investigated — **a factor-of-2 gap against an independent measurement is a defect report, not a
> rounding difference.** Plotting the data is what exposed it; drawing the axis forced the question
> "what is x, actually?" — the table never did.

Two consequences of the window-average shape that are easy to conflate and differ by 15% here: the
cost of **one** item when the accumulated state is already N is `a + b·N`, while the **average** cost
per item of a run that processes N is `a + b·N/2`. The general rule: when the measurement is an
average over a window and the independent variable moves *during* that window, regress on the
window's **mean**, never on an endpoint or a per-run proxy. Fits and evidence in
`we-m2bench/evidence/run{1,5}/timing.json`, `decode_device.tsc.per_round[]`.

*Why this matters beyond bookkeeping:* the `L = 8192` three-way arithmetic multiplies a single
decode anchor by `L`. That understates the long-context lanes. The ordering probably survives
(the correction pushes force-decode and re-prefill the same way) but the margins do not — S3
has to sweep `L` with a context-dependent cost.

**Prefill: quote the 56.91 ms floor, never a tok/s.** All 8 spans are 56.911–56.913 ms
(spread **0.003%**) while the tok/s column spans 369.0–632.6 (spread **57.7%**). With
`CHUNK_SIZE = 256` the device computes one full 256-position chunk whatever the prompt length,
so the tok/s variation is entirely numerator-driven. At these prompt lengths prefill is a fixed
cost, not a rate — and its "throughput" column is a trap for anyone reading the file cold.

## Where the code and artifacts live (as of 2026-07-28)

Local:

| path | what |
|---|---|
| `/home/lexu/WaferEngine-staging` | main repo, branch `lexu/staging/kv-feature` (the M1 line). The durable planning docs live here and are **not git-tracked** — they persist via this memory repo and ContextBase. |
| `/home/lexu/we-m2bench` | the M2 benchmark worktree, branch `lexu/staging/m2-benchmark` locked at `a3a509c`, **zero source changes**; `evidence/run{1,5}/` holds the two completed runs. |
| session scratchpad | `timing_diff.py` (242-leaf field-by-field diff), `golden_check.py`, and the remote drivers `m2_compile.sh` / `m2_serve.sh` — deliberately **not** committed, so S0 stays zero-diff. |
| `/home/lexu/we-p2`, `we-fdbench`, `we-pr14-compile`, `/home/lexu/WaferEngine` | older worktrees from earlier sessions, unrelated to M2. |

On CS-3, everything under `/home/eidf217/eidf217/congjiehe/lexu/m2bench/` (Le's instruction —
do not scatter artifacts elsewhere):

| subdir | what |
|---|---|
| `serving_cache/serve_2x4_8k20k/` | the compiled store, **6.3 GB** (prefill 3.2 G + decode 3.1 G + tokenizer 11 M + `build_manifest.json`). Reusable for S1–S3 unless a kernel changes. |
| `we-m2bench-rsync/` | the synced code tree (9.3 MB) |
| `hf/qwen3-1.7b/` | weights: safetensors symlinked to `WaferServe/models/qwen3-1.7b`; the tokenizer files were missing there and were uploaded from the local HF cache |
| `evidence/run1 … run5/` | per-run `timing.json`, `results.json`, verdicts, trace |
| `logs/` | compile + all 5 serve logs, including the 3 infrastructure failures in full |

38 GB of regenerable staging was deleted after the runs; the work repo and the M2 worktree are
**intentionally uncommitted** — Le owns commits.

## Updates

### 2026-08-06 — measured `runtime.load()` (ELF→wafer) cost, and load ≠ attach

Drained from `memory/inbox/2026-08-06-runtime-load-onchip-artifact-upload-cost.md` (author claude).
This note records the number the "untimed bracket" above left out: the `runtime.load()` step
itself, worker-local, after the 6.6 GB gateway→worker staging.

- **`runtime.load()` IS directly timed** — `perf_counter` wraps the exact call and stores `load_s`
  (`launch_prefill.py:1939-1943`, `launch_decode.py:4066-4067`; prints "runtime.load took Xs",
  comment "ELF -> wafer program+weight load"). NOT a bracket/subtraction estimate.
- **Measured `load_s` (real CS-3, worker node, artifact already staged local, pdSeparate):**
  - M2-S0 / mtbench8: prefill **141.47 s**, decode **150.67 s**
    (`request_config/mtbench8/timing.json`, `device_verdict.json`).
  - E10 A/B run: prefill **146.01 s**, decode **156.04 s**
    (`assets/2026-07-31-e10-ab-boundary/e9_timing.json`).
  - ⇒ **~140–156 s per artifact**, decode consistently a few s higher.
- **`load` ≠ `attach` — separate stages.** `runtime = SdkRuntime(...)` (attach) is **UNTIMED** and
  lives in the ~416 s bracket (interpreter start + artifact `copytree` + attach); `runtime.load()`
  is separately measured as `load_s`. So the M2-S0 734 s run decomposes as **load ~292 s
  (141.5+150.7, measured) + untimed bracket ~416 s + compute ~26 s** (mtbench8 short gen). An
  earlier pass that folded the ~150 s load *into* attach **double-counted** — corrected here.
- **Caveat:** `load_s` is **program + weights together** (weights baked into the ELF), not code-only
  `.text`. ~150 s is "whole decode artifact onto the wafer", NOT a per-kernel code-upload figure —
  do **not** use it as the reference for a MeshJIT / on-chip PE→PE single-kernel `.text` fetch (a
  few KB over the fabric, a completely different order of magnitude).
- Estimation corollary: Gate 3 is decode-only reload ⇒ **ONE ~150 s `load_s`, not two.**

Pointers: `launch_prefill.py:1654,1939-1943`; `launch_decode.py:3594,4066-4067`;
`we-m2bench/.../request_config/mtbench8/{timing.json,device_verdict.json}`;
`assets/2026-07-31-e10-ab-boundary/e9_timing.json`.
