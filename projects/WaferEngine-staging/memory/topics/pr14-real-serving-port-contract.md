---
summary: PR #14 (WaferAGI, "Real Qwen3 1_7B Serving") pre-integrates the standalone multi-round/varlen/round_reset/KV-bridge machinery into both fused deployments; only the keyed-retain KV store is still a gap. Investigation report backing the M0/S2 port contract, plus the branch map and the measured trial-merge cost of rebasing kv-feature onto it.
tags: [waferengine-staging, qwen3, pr14, serving, port-contract, kv-reuse, nc-service]
---

# PR #14 Real-Serving Integration & M0/S2 Port Contract — Investigation Report

> ## Branch map — which local ref is which (audited 2026-07-28 via reflog)
>
> Two local branches track this same upstream line at **different points in time**. Getting
> them confused costs real measurement error, so check the tip before quoting any of their
> recorded timings.
>
> | local ref | fetched from | tip | date |
> |---|---|---|---|
> | `pr14-real` | `github.com:CongjieHe/WaferEngine.git` branch `real_qwen3_1p7` | `efa954d` | 2026-07-21 |
> | `pr14-head` | `WaferAGI/WaferEngine` `refs/pull/14/head` | `a3a509c` | 2026-07-28 |
>
> **Re-checked 2026-07-28 (later the same day, `git ls-remote` + GitHub compare API): the two
> upstream lines have CONVERGED at `d9dbeec`.** Both `WaferAGI refs/pull/14/head` and
> `CongjieHe real_qwen3_1p7` now point at it, so `pr14-head` is 1 commit behind and
> `pr14-real` is 6. That single commit ("4B Decode Optimization") touches **only
> `models/qwen3_4b-decode/`** — `decode.csl`, `comm_pe.csl`, `approx_math.csl`,
> `oracle_fp16.py`, `check_approx_math.py` — and nothing in `qwen3_1p7b-e2e-pdSeparate`, so it
> is provably neutral for pdSeparate measurement. **M2 deliberately stays locked at
> `a3a509c`**, the commit that produced the reference `mtbench8/timing.json`, so that
> "reproduce the baseline" compares like with like. See [[m2-s0-baseline-and-timer-provenance]].
>
> **`pr14-real` is an ancestor of `pr14-head`, 5 commits back.** Those 5 commits rewrite the
> 1.7B pdSeparate kernels (`decode.csl`, `ht_head.csl`, `ht_tail.csl`, `prefill.csl`; ~12.4k
> insertions) and change two things that dominate any host-side measurement:
>
> - `per_round_kv_load_ms` **5290 → 69.5 ms** (disk `.npz` read, ~76×); KV handoff per prompt
>   **2.94–3.12 s → 0.72 s**; `total_wall_s` 1230 → 734.
> - `serve_2x4_8k20k.json` now **freezes the host-stream `io_loc` pins**
>   (`KV_EGRESS_IO_LOCS` / `KV_INGRESS_IO_LOCS` / token / logits), described in-file as
>   "frozen to the device-validated auto placement (mtbench8 8/8 bit-identical)" — closing a
>   known ~3× auto-placement bandwidth loss (see [[h2d-host-device-bandwidth]]).
>
> **What did NOT move across those 5 commits:** decode 659.4 → 655.0 µs/token device,
> prefill 30-token span 57.03 → 56.91 ms, KV egress 22.31 → 23.53 ms — all within ~1%. So the
> device-side anchors are stable and the delta is entirely host-side overhead.
>
> ⇒ **Baseline new work on `pr14-head`.** Using `pr14-real` measures two already-fixed
> implementation artifacts and charges them to the architecture. *Caveat:* `pr14-head` also
> carries "Qwen3 1p7b Speculative Decoding" and "4B Decode Optimization", so it is less settled;
> `pr14-real` is the known-good fallback, but then subtract the disk and `io_loc` effects by hand.
> *Unknown from here:* whether `real_qwen3_1p7` has moved since it was last fetched — re-fetch
> rather than assume. Related: [[git-branch-status-verification]].

Session **2026-07-11 (M0/S2)**. Read-only dig across three fronts:
(1) standalone `qwen3_1p7b-decode`/`-prefill`, (2) integrated `qwen3_1p7b-e2e`/
`-e2e-pdSeparate`, (3) the `nc_service/waferengine/` runtime skeleton. This note is
the **findings/background**; the formal **S2 port contract** (inputs/outputs,
invariants, colors/queues/DSDs, correctness assumptions) lives in
`milestones/M0-reuse-foundation.md` (durable planning doc = source of truth).
Related: [[standalone-vs-integrated-kernel-parity]], [[kv-cache-policy-tradeoffs]],
[[e2e-kernel-dataflow-and-topology]].

## Refs (all evidence pinned)

- `fcfc8c1` = `origin/main` (happyandslow) = `waferagi/main` — **identical commit**;
  this is the CURRENT integrated snapshot the staging repo derives from.
- `waferagi/pr14` = `b9ff52b` = PR #14 "Real Qwen3 1_7B Serving" (base `fcfc8c1`,
  **still OPEN**, on WaferAGI/WaferEngine, **not merged into origin/main**). 322 files,
  +47k/−33k. The up-to-date standalone kernels + a full real-serving stack.
- Repo used for diffs: `/home/lexu/WaferEngine` (has a `waferagi` remote; PR head
  fetched to `waferagi/pr14`).

## Headline (this reshapes M0)

**PR #14 already absorbs the standalone's varlen multi-round KV ingress + `round_reset`
lifecycle + per-round host→decode KV injection into BOTH `e2e` and `pdSeparate`.** At
`fcfc8c1` the integrated homes had zero multi-round machinery (verified: 0 hits for
`round_reset`/`NUM_ROUNDS`/`PREFILL_LENS`); at `pr14` both have it. So M0's planned
"port the standalone mechanism into integrated" (subtasks S4/S5) is **largely done
upstream, pending merge** — *if* we adopt PR #14 rather than re-port by hand.

**The one M0 deliverable PR #14 does NOT provide is the keyed retain-not-discard KV
store.** PR #14's multi-round serving is per-request **isolation** (each round re-ships
the same fresh KV; `round_reset` rewinds and discards decode-appended KV; the host even
asserts same-prefill rounds are bit-identical). `XKCache_tile`/`XVCache_tile` are indexed
`(layer,batch,col)` only — no request/prefix key dimension. So M0's residual work =
build the keyed-retain layer **on top of** PR #14's plumbing, not port the plumbing.

> **Decision deliberately DEFERRED** (per Le): whether to migrate to PR #14 (rebase
> staging onto it) vs hand-port select pieces is a separate step, taken only after this
> report. This note documents the contract so that decision can be made cheaply.

## What PR #14 integrated into the fused deployments (feature matrix)

Rows = feature; cells = present/absent @ ref, with a representative anchor. `@pr14`
paths are on `waferagi/pr14`.

| Feature | e2e @fcfc8c1 | e2e @pr14 | pdSep @fcfc8c1 | pdSep @pr14 |
|---|---|---|---|---|
| Multi-round serve loop | absent | **present** (`launch.py` `num_rounds`/`PREFILL_LENS`; device `decode.csl` round tasks) | absent | **present** (prefill-once+decode-once, `NUM_ROUNDS=N`) |
| `round_reset` lifecycle | absent | **present** (`src/decode/decode.csl:260`, `round_barrier :284`) | absent | **present** (shared decode.csl) |
| Varlen prefill at runtime | absent (compile-time `PREFILL_LEN`) | **present** (runtime chunk/len peel) | absent | **present** |
| Chunked prefill | absent | **present** (`prefill.csl` chunk loop, `CHUNK_SIZE`) | absent | **present** |
| Per-round host→decode KV injection | mock only | **present** (`host/kv_bridge.py` + `kv_ingress_adaptor/injector` + `kv_egress_colmux`) | single-shot fixed `kv_mux`/`kv_adaptor`/`kv_demux`, `KV_TRANSFER:1` | **present & reworked** — old files DELETED, replaced by e2e's ingress mechanism |
| **Keyed / retained KV store (retain-not-discard)** | **absent** | **absent** (0 real hits; caches keyed only by layer/batch/col) | **absent** | **absent** |
| Real HF weights + numpy oracle + tokenizer | absent (`host/` empty) | **present** (`host/hf_weights.py`, `qwen_tokenizer.py`, `SafetensorsReader`; mock retained if `weights_dir=None`) | absent | **present** |
| EOS early-stop | absent | **present** (`ht_tail.csl`, `enable_early_stop`, `eos_token_ids`) | absent | **present** |
| Numerics (fast rsqrt/recip, fp32 softmax/RMSNorm) | absent | **present** (`decode.csl:228/236`, f32 RMSNorm) | absent | **present** |

Nuance on "real weights": PR #14's title "Real Qwen3 1_7B Serving" = the **real Qwen3
architecture** (GQA, per-head QK-RMSNorm, RoPE, tied embeddings, vocab 151936, HF EOS
`[151645,151643]`) + a real HF weight loader wired **into the integrated homes**. The
**standalone** `-decode`/`-prefill` are still **mock/seeded RNG weights** at pr14 (grep
`from_pretrained|safetensors|transformers` over both standalone dirs @pr14 = 0 hits).
So real weights arrived in the integrated homes, not the standalone kernels.

`qwen3_4b-e2e-pdSeparate` (new in PR #14) is a real second deployment using the **same**
`kv_ingress_adaptor`/`kv_ingress_injector` bridge, scaled to Qwen3-4B — confirming the
ingress/injector bridge is now the common pattern across all integrated deployments.

## Standalone kernel changes fcfc8c1 → pr14 (the contract source)

The standalone already had the machinery at `fcfc8c1`; **PR #14 hardened it, it did not
introduce it.** Biggest structural change: the `kv_stream_ingress` / `KV_TRANSFER`
**compile-time bake gate was removed** — streaming KV ingress is now **unconditional**
(no bake path). Also:
- `decode.csl`: deleted `param prefill_len_per_pe` and `param kv_stream_ingress`; every
  `if (kv_stream_ingress != 0)` guard gone; main loop `n_steps → n_steps+1` (adds a
  terminator/flood step). `round_reset` moved **265 → 254**, `round_barrier` **287 → 272**.
- `decode launch.py`: deleted the `KV_TRANSFER` toggle + bake path (adaptor/injector
  always built); ports sized for **one** round (device self-re-arms per round); varlen
  per-round transfer + u16 guard; `PREFILL_LENS` overlay moved to `request_config/*.json`.
- `prefill.csl` / `prefill launch.py`: removed `param kv_egress` gate (egress
  unconditional); added a serve-loop re-arm barrier so the next request's queue reconfig
  can't race in-flight egress. Egress color/order/packing **unchanged**.

## The three mechanisms — condensed technical map

Formal contract in `milestones/M0-reuse-foundation.md`. Anchors here are on
`waferagi/pr14`, `models/qwen3_1p7b-decode` unless noted.

**(1) Varlen prefill→decode KV ingress.** Device path: `host stream (TOP) →
kv_ingress_adaptor (1×1 per Y-band) → kv_ingress_injector (1×P_BLOCK_SIZE) → decode
block east edge → west-shift → each PE's XKCache_tile/XVCache_tile` (`decode.csl:124-129`).
Varlen seed = a phase-0 metainfo tile: `KV_META_LEN=2` i16 (one 32-bit wavelet), slot0 =
`prefill_len_per_pe` (`decode.csl:1515-1523`). Peeled in `kv_ingress_meta_phase()` →
`prefill_len_per_pe_rt = kv_meta_buf[0]` (`:1528-1535`; var decl `:76`). Every KV DSD is
narrowed from compile-MAX to `_rt` via `@set_dsd_length` local clones (`:1537-1582`) —
"runtime COUNT × comptime length" discipline; buffer stays MAX-allocated, only live
extent/strides shrink. Adaptor/injector segment the KV into `n_segs_rt` back-to-back
`seg_len` wavelets because a single fabric DSD extent ≥ 0x7FFF hangs silently (transport
limit, **not** chunked-prefill).

**(2) Per-round host→decode KV injection (T2 reload).** Transport = a runtime input
**STREAM** (not memcpy/set_symbol): one stream per Y-band, `NS = P_Y_BLOCK_NUM` bands.
Single `runtime.run()`; per-round loop `for rnd in range(num_rounds)` re-arms the resident
device — **no per-round launch/RPC**. Each round: compute decode budget → `_repack_kv_band`
(varlen, no MAX pad; per injector row N→S: `Pw` metatiles W→E, then per layer **K then V**,
cols W→E; K tile `[b][f][p]`, V tile `[b][p][f]`) → send all NS KV streams nonblock → send
X[0] blocking → drain `n_rnd` logit receives → drain TSC. Device re-arm borrows IQ7/OQ7
from `broadcast_color`(5), flipped by the `kv_ingress_oq_empty` handler flag
(0 = ingress→broadcast→`kv_ingress_resume`; 1 = broadcast→ingress→`round_reingress`)
(`comm_pe.csl:1344-1376`).

**(3) `round_reset` lifecycle.** `fn round_reset()` (`decode.csl:254`) rewinds
`n_steps=(kv_len_per_pe − prefill_len_per_pe_rt)*P_BLOCK_SIZE`, re-seeds RoPE from (1,0)
(no cross-round drift), sets per-layer `iter_num_bank[li]=prefill_len_per_pe_rt`,
`step_bank[li]=0`. `fn round_barrier()` (`:272`) is a Y-axis all-reduce gating the
broadcast→ingress rebind. Device task chain per round: `main()` → `round_barrier()` +
`kv_rebind_to_ingress_flush()` → `round_reingress()` → `kv_ingress()` (re-peel meta +
re-load KV) → `kv_ingress_resume()` → `round_reset()` → `@activate(main_id)`. **Still
isolation, not retain+extend** — host re-ships the SAME KV each round; decode-appended KV
discarded.

**The retain seam (where M0's keyed layer attaches):** make `round_reset` conditionally
**retain + extend** (skip the `iter_num_bank`/`step_bank` rewind on a cache hit, keep the
prior slab and grow `iter_num`) and have the host inject a **retained prior request's**
KV (from a keyed store) instead of a fresh prefill's KV. Both are policy/lifecycle
changes layered on the existing transport — the transport itself needs no change.

## nc_service runtime skeleton — reuse map for a standalone `samples/` deployment

`/home/lexu/nc_service` @ `lexu/specdec-real-kernels`. Its `waferengine/` is a **strict
superset** of the staging repo's `waferengine/` (backbone-only + mock). It is a
**speculative-decoding drafting service** (CS-3 = draft model, external GPU = verifier),
not a standalone inference deployment — but its transport backbone + real-kernel driver
are directly reusable.

**Backbone `engine/io_pipeline/` (reuse as-is, all generic):** `frame.py` (wire codec),
`gateway/bridges.py` (`LocalShellBridge`/`LauncherBridge`/`InProcessPatchBridge` +
`ExchangePump`), `executor/{executor_daemon,fifo_server,serve_core,appliance_session}.py`,
`executor/inproc_patch/`. Request flow: `remote svc → gateway (ExchangePump →
LauncherBridge) → executor (executor_daemon → fifo_server → serve_core) →
ApplianceSession.send → WSE-3`. Staging is missing `serve_core.py` + `inproc_patch/` +
`InProcessPatchBridge` (nc_service filled these seams).

**Real-kernel driver `samples/specdec/model_adapter/` (reuse as-is):** the key
abstraction. `appliance.py` `DecodeAppliance`/`PrefillAppliance` drive the **real
`launch.py` build verbatim** via `_reuse_real_launch_build` — a monkeypatch that runs
`launch_mod.run(cfg, cmaddr=None)` up to (not including) `SdkLayout.compile`, unwinding via
a `_BuildComplete` raise, then compiles/loads/runs **once, resident**. Per-round host→
decode KV injection lives in `exchange_batch` (re-sends KV band + X[0] seed), transcribing
decode `launch.py:2490-2525`. `kv_transform.py` = pure-numpy prefill-egress→decode-ingress
layout transform (the host transform neither kernel ships). `pdsep_proto/kv_handoff_codec.py`
= KV blob (de)serialize. `kv_channel.py` (+ `rdma_backend.py`) = disk-free request_id-keyed
KV transport (TCP N-stream + RDMA backend).

**Spec-dec-specific (replace/drop for a standalone deployment):** `proto/*` +
`translate.py` (draft/verify gRPC wire — drop); `gateway_frontend.py` `run_session`
(dials GPU verifier, drives `draft_len` — replace with prompt-in/tokens-out frontend);
`codec.py` `encode/decode_request_payload` (verdict payload `[flags,n_acc,corr…]` —
replace with `[prompt_len, token_ids…]`; keep `derive_counts`/`kv_bytes`);
`decode_adapter.py` rewind fold (`num_accepted`+corrections — replace with plain
autoregressive append); `mock_verify_host.py` (drop).

**Standalone `samples/standalone/` sketch (design only):** compose the reused backbone +
`model_adapter/appliance.py` + `kv_transform.py` + (`kv_channel.py` if PD-disaggregated)
+ vendored kernels; add glue: `serving_codec.py` (prompt in / token out), a standalone
`decode_adapter` (round 0 = full-ingress seed, round r>0 = append sampled token, re-arm at
`cached_len+1`, no rewind), a standalone `prefill_adapter` (real prompt tokens), a
`build_handlers` that keeps the role→map dispatch but drops the verify fold, a
`frontend.py` (prompt-in/tokens-out loop to EOS/max_len), and an adapted `driver_main.py`
(keep staging + bridge + pump; drop draft-len/verify-reachability). Replay safety is free
from `serve_core.ReplayState`.

## Corrections to prior recorded facts

- **`standalone-vs-integrated-kernel-parity`** is now materially stale for the *integration
  target*: PR #14 closes gaps #1 (multi-round), #2 (varlen), #3 (chunked prefill), #4 (EOS),
  #8-9 (numerics), #11 (oracle/real weights) **for the integrated homes**. Kept: those gaps
  are still real vs `origin/main` (unmerged), and the standalone kernels themselves are
  still mock-weight. See that note's updated tail.
- **kickoff_relay.csl is NOT on the KV egress path** (prior parity-note item #5 implied it
  was). It relays the forward-start timing sentinel (demux PE0 → HT_tail TSC). The real KV
  egress chain is `prefill.csl` (switch-gather EAST, `start_kv_egress`) →
  `kv_egress_colmux.csl` (column-mux drain NORTH, extended by transparent `kv_fwd.csl`) →
  host stream.
- **`PREFILL_LENS` relocated** `model_config/*.json` → `request_config/*.json` (pr14).
  `model_config/*.json` now carries `MAX_SEQ_LEN`/`CHUNK_SIZE` only.
- **round_reset/round_barrier line numbers** are `254`/`272` on pr14 (`265`/`287` on
  fcfc8c1 — still correct for what staging currently builds).

## 2026-07-12 update (M0/S4 design digs) — pr14 e2e is HOST-MEDIATED; adopt-vs-port splits by concern

Four read-only digs while designing M0/S4 reshaped the adopt picture. **Key correction to
this note's headline:** where the S2 investigation said pr14 "already absorbs the machinery
into both e2e and pdSeparate" (true), it did **not** flag that pr14 *also* **converts e2e's KV
path from on-chip relay to host-mediated**. It does.

- **e2e@pr14 is host-mediated (prefill→host DRAM→decode).** New `src/prefill/kv_egress_colmux.csl`
  (D2H) + host `host/kv_bridge.py::transform_egress_to_inj` + new `src/decode/kv_ingress_adaptor.csl`
  / `kv_ingress_injector.csl` (H2D). `relay.csl` is byte-identical to fcfc8c1 but **inert**
  (`KV_TRANSFER` default 0). e2e latency at pr14 literally includes a host stage:
  `e2e_ms = pf_us + kv_bridge_ms + dec_us`.
- **The on-chip relay is NOT config-revivable at pr14.** `param kv_transfer` + `kv_xfer_color_0/1`
  deleted from BOTH kernels; `set_param … kv_transfer` count = 0; decode `init_task_t`
  (`decode.csl:1746`) calls host-only `kv_ingress()` unconditionally (no seam-ingress branch);
  `KV_TRANSFER=1` only paints colors 17/21 that nothing feeds/consumes, and those ids collide
  with the host path. Reviving = re-port the removed on-chip machinery (reference = staging's
  live fcfc8c1 e2e), not a toggle.

  > ⚠️ **The two bullets above are contested by an unconfirmed 2026-07-28 correction.** A direct
  > diff of `main` vs `a3a509c` found that in **`qwen3_1p7b-e2e`** the on-chip relay was **never
  > demoted by PR #14** and was already config-revivable on `main` (three `KV_TRANSFER: 1` configs
  > shipped, `build_relay` identical, `src/relay.csl` still present at PR #14); the "host-mediated,
  > not config-revivable" reading appears to hold for **`e2e-pdSeparate`** only. Evidence and status
  > in [[standalone-vs-integrated-kernel-parity]] § 2026-07-28. **Not confirmed by Le** — treat both
  > readings as live until someone re-diffs, and re-check any adopt-vs-port reasoning that used
  > "adopting PR #14 means host-mediated e2e" as an input.
- **e2e and pdSeparate KV transport are byte-identical at pr14** (matching blob hashes on
  `kv_bridge.py` / `kv_egress_colmux` / `kv_ingress_adaptor+injector`). Differences are packaging:
  e2e = 1 co-resident artifact / 1 runtime / in-memory per-request KV / no swap; pdSeparate = 2
  artifacts / **sequential load on the SAME one card (same cmaddr, time-multiplexed — not two
  cards, not host-to-host)** / disk-`.npz` phase-batched / ~105 s binary swap / larger per-half
  capacity. (Refines the "prefill/decode as separate device artifacts bridging KV through host
  memory" description — it's one card + disk, not two pods.)
- **Why the relay was dropped: capability, not a bug.** The static, meta-less, single-shot seam
  cannot carry varlen + per-round meta tile + re-arm; all that lives in the host injector. The
  whole e2e rework is one squashed commit "Real Qwen3 1_7B Serving" (thin documented rationale;
  strong inferred-from-structure reason). A device run would validate/measure, not diagnose.
- **Standalone `qwen3_1p7b-decode` is multi-round but ISOLATION, not retain** (`round_reset`
  `decode.csl:265-281` rewinds counters + re-seeds RoPE; host re-ships KV each round; bit-identical
  assert forbids retain). **PE-internal retain is demonstrable on standalone decode alone** (slab
  SRAM-resident; gate the rewind + host stops re-shipping; no relay/bridge).

**Plan impact (M0 Phase C re-decomposed 2026-07-12, in the durable docs = source of truth):**
two lines — **Line 1 = PE-internal retain (S6, standalone-demonstrable)**, **Line 2 = KV transport
(S4 e2e / S5 pdSeparate)**; S4/S5/S6 are **peers** (S6 done first, S5 under separate active dev).
**S4 = build a metadata-carrying *on-chip* relay** (embed per-round meta + link to KV, reuse pr14's
injector *logic* but source KV over fabric) — **NOT** adopt pr14's host-mediated e2e (which abandons
the no-offload corner) and **NOT** revive the static `relay.csl` wire. The rest of the pr14 stack
(multi-round loop, varlen, chunked prefill, real weights, EOS, fp32 numerics) stays a live
adopt-vs-port candidate (KV-source-agnostic). Full detail: `milestones/M0-reuse-foundation.md
§ Phase C` + Verification log; `GOALS.md §7` adopt-vs-port entry (refined). Related:
[[kv-cache-policy-tradeoffs]], [[e2e-kernel-dataflow-and-topology]], [[standalone-vs-integrated-kernel-parity]].

## 2026-07-28 — what the rebase onto PR #14 actually costs (trial merge)

You are sizing the rebase of `kv-feature` onto PR #14 and you run a trial three-way merge to find
out what it costs. **The conflict list is the cheap half.** The expensive half is the files git
merged without complaint, because our work and PR #14's work touched *different lines of the same
contract*.

Conflict surface, measured on a trial merge against `a3a509c`: **7 files, 18 hunks, ~650 lines** —
`decode/launch.py` (6 hunks, 457 lines), `decode/src/ht_tail.csl` (3/53),
`decode/src/decode.csl` (2/34), `decode/src/ht_head.csl` (1/24), `prefill/launch.py` (3/52),
`prefill/src/ht_head.csl` (2/21), `prefill/model_config/test_sim_2x4_kv_varlen.json` (1/8). Budget
it in days, not weeks — but budget it *after* the two breaks below, not before. **These counts
expire**: PR #14 moves (`b9ff52b` → `a3a509c` while this repo's docs still pinned the old one), so
re-run the trial merge at the then-current tip.

Two structural facts in that table matter more than the totals:

- **The entire M1-S1 slot-addressing seam produces ZERO conflicts.** The piece nobody upstream is
  building is also the piece that costs nothing to carry ([[m1-s1-multi-slot-kv-seam]]).
- **The recurring friction is thematic, and it will recur on every future rebase.** PR #14's repeated
  move is *deleting* compile-time switches (`kv_stream_ingress` in decode, `kv_egress` in prefill —
  those paths now unconditional), and our retain code sits inside exactly those conditionals. We add
  conditionality precisely where they remove it.

**Break 1 — a renamed symbol survives as a dangling import (code-verified in the merged tree).**
PR #14 renames `numpy_oracle_logits` → `numpy_decode_oracle`. `oracle_fp16.py` auto-merges with
**no conflict**; the merged `launch.py` then carries both `from oracle_fp16 import
numpy_oracle_logits, numpy_oracle_retain_step0` (ours, now dangling) and `from oracle_fp16 import
numpy_decode_oracle` (theirs), while the merged `oracle_fp16.py` no longer defines the old name.
Git did its job; the result does not import. Before the rebase, enumerate PR #14's renamed symbols
and grep our call sites — this whole class is invisible as a conflict.

**Break 2 — a protocol split across two files can merge *half*** `[unverified]`. S6b widened the
decode round header to a 2-wavelet `[N, F]`; the sender is in `ht_head`, the receiver in `ht_tail`.
Both files conflict, so both get hand-resolved **independently** — take the widened header at one end
and not the other and you have a wavelet-count mismatch, the classic silent CSL desync with no
compile error. What makes it worse: **`bsz = 2` in every config we own**, which is claimed to make a
half-merge produce plausible-looking output rather than an obvious failure. *That half is reasoning
from the merged sources, not an observed run* — treat it as the reason to add an explicit check, not
as a measured fact. Concretely: after resolving, assert the sender's emitted wavelet count equals the
receiver's expected extent, and add at least one config where a mismatch cannot cancel.

Adjacent guard in the same area, also **reasoning-only** `[unverified]`: PR #14 adds an `n_steps + 1`
terminator step to both `ht_head` and `ht_tail` loops. Tracing both counts, the S6b balance survives
— `ht_head` floods `NEG_INF` and breaks **without draining a token**, and `ht_tail`'s pre-existing
`tail_step < n_steps - 1` gate already excludes the terminator from emitting, so N−F emits still meet
N−F drains. But **branch order in the merged `ht_head` matters**: if our `ht_step < forced_decode_len`
branch precedes the terminator check, `F > N` swallows the terminator entirely (no flood, no break)
and the diagonal PE blocks forever on a `pre_embed_x` the host never sends. `F == N` is safe. Put the
terminator check first *and* assert `F <= N` host-side.

The generalisable half of this — a three-way merge reconciles lines, not a contract spread across
files — lives in [[git-branch-status-verification]]. Conflict counts and the dangling-import break
are code-verified against an actual trial merge; nothing here was confirmed by Le, and the rebase
itself remains the deferred adopt-vs-port decision above.

## Last updated

2026-07-28 (trial-merge rebase cost + the two clean-merge breaks; contested-e2e-relay caveat added.
Prior: 2026-07-12 M0/S4 design digs, which superseded the "e2e stays on-chip under pr14" implication
of the 2026-07-11 headline).
