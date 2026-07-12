---
summary: PR #14 (WaferAGI, "Real Qwen3 1_7B Serving") pre-integrates the standalone multi-round/varlen/round_reset/KV-bridge machinery into both fused deployments; only the keyed-retain KV store is still a gap. Investigation report backing M0/S2 port contract.
tags: [waferengine-staging, qwen3, pr14, serving, port-contract, kv-reuse, nc-service]
---

# PR #14 Real-Serving Integration & M0/S2 Port Contract — Investigation Report

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

## Last updated

2026-07-11 (M0/S2 investigation).
