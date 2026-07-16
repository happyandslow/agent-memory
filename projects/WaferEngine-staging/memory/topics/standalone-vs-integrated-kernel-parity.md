---
summary: Feature-parity gap between current standalone qwen3 kernels and integrated e2e/pdSeparate snapshots.
tags: [waferengine-staging, qwen3, kernel-parity, serving]
---

# Standalone vs Integrated Kernels — Feature Parity Gap

What the **integrated** end-to-end models (`qwen3_1p7b-e2e`, `qwen3_1p7b-e2e-pdSeparate`)
do NOT support relative to the **standalone** kernels (`qwen3_1p7b-decode`,
`qwen3_1p7b-prefill`), which are the more up-to-date source of truth. Session
2026-07-05 (CSL + launch.py diffs across the three homes of each kernel), with a
2026-07-09 correction from a direct `qwen3_1p7b-e2e` source read.

## Provenance (why they diverge)

- Integrated e2e + pdSeparate were introduced **only in commit `fcfc8c1` (PR #13)**
  as wholesale copies. The standalone kernels have a longer lineage — notably
  `e7d8635` **"qwen decode accuracy fixes (#12)"** — that the copies were seeded
  *before*.
- Integrated **`decode.csl` is byte-identical between e2e and pdSeparate** (md5
  `71d80bba…`) and differs from standalone (`c9bee9f5…`; 572 del / 310 add lines).
  Same for prefill (heavy divergence: comm_pe 785 lines, ht_tail 262). The two
  integrated homes share one frozen snapshot; they differ from each other ONLY in
  KV-transfer plumbing (e2e relay vs pdSeparate demux/mux).
- **2026-07-09 correction:** current e2e `decode.csl` is no longer the originally
  pinned `71d80bba` snapshot; the direct read observed md5 `05cc76d4` and Qwen3
  QK-Norm + fp32-accumulate GEMV (`@fmachs`) present. The serving gaps below still
  hold, and one numerics gap remains: e2e decode exponentiates softmax scores in
  bf16 while standalone keeps exp/sum/normalize fully in fp32.
- So the gap is: standalone = current, verified, feature-rich; integrated = a
  frozen older fork that added integration wiring but dropped serving/accuracy/
  verification features.

## NOT supported in integrated (the gap)

### Serving / capability
1. **Multi-request / multi-round serving from one loaded artifact.** Standalone
   runs a `NUM_ROUNDS`/`PREFILL_LENS` serve loop — one `load()`+`run()`, then N
   back-to-back requests with per-round re-arm (decode `round_reset`
   `decode.csl:206`, `round_barrier` `:285`; prefill serve loop
   `prefill launch.py:1464-1546`). **Integrated = 0 hits, gone (not dead code).**
   → An integrated artifact serves **exactly one request per compiled load**; a
   second request needs relaunch/recompile.
2. **Variable prefill length at runtime.** Standalone peels runtime metainfo
   (`prefill_len_per_pe_rt`, `request_n_chunks`); configs carry
   `PREFILL_LENS:[8192,4096,8192,4096]`. Integrated hard-compiles a single scalar
   `PREFILL_LEN` (e2e 256, pdSep 2048). → prompt length is fixed at compile time.
3. **Chunked prefill.** Standalone processes prompts up to `MAX_SEQ_LEN=8192` in
   256-token causal chunks with KV/RoPE banked `[layer][chunk]` (`prefill
   launch.py:246-262, 720-727`). Integrated is a single flat pass. **This is the
   root cause of the ~512-token prompt cap** in [[e2e-pdSeparate-device-validation]]
   — chunking is exactly what spreads the quadratic score/mask buffer that
   currently caps (and overflows) the integrated prefill.
4. **EOS early-stop.** Standalone decode floods a `STOP_THRESHOLD_F16` sentinel to
   exit on EOS (`eos_token_ids=[151645,151643]`, `enable_early_stop`, `*_eos.json`
   configs). **Integrated: absent** (no logic, no config) → always emits exactly
   `max_output_len` tokens.
5. **Full KV egress to host (prefill), varlen + re-armable.** Standalone
   `kv_egress_colmux.csl` + `kickoff_relay.csl` + `kv_fwd.csl` stream the full KV
   to `P_Y_BLOCK_NUM` host streams with varlen peel + a `round_sync` re-arm
   barrier + bit-exact sim self-check. **e2e has NO host egress** (relay only);
   **pdSeparate has a simpler fixed `kv_mux.csl`** (no varlen, no re-arm) and it's
   **not wired into any shipped config** (all use `KV_TRANSFER:1`, none set
   `KV_EGRESS`).
6. **Tall (≥3 block-row) layouts.** Standalone ships **2×4** device configs and
   the relays for >2 block-rows (`kickoff_relay`, `kv_fwd`). Integrated hardcode
   the **2×2** seam (relay colors 17/21 at one fixed gap) and ship no ≥3-row
   config. → the "taller layout raises the prompt cap" lever is unavailable in
   integrated as-shipped.
7. **GQA head-dim-pad wide sharding.** Standalone splits `attn_per_pe`/`kv_cols`/
   `gqa_group_size` from the hidden shard (supports e.g. padded head_dim);
   integrated collapse to `dim_per_pe`. No-op for the shipped Qwen3-1.7B geometry
   but a structural capability only standalone has.

### Numerics / performance
8. **Softmax precision residue.** Standalone does max-subtract/exp/normalize in
   fp32 (`decode.csl:324-334,1249-1274`). Current e2e has closed much of the old
   numerics gap, but its decode softmax still exponentiates in bf16
   (`@map(fast_exp, score_dsd, score_dsd)`), keeping only the denominator f32;
   standalone keeps exp/sum/normalize fully in f32. Prefill softmax is full-f32.
9. **#13 fast rsqrt/recip Newton iteration** (`decode.csl:227-249`). Integrated: 0
   hits → pays soft-float `__divsf3` division cost on every reciprocal/norm.
10. **Dedicated Score×V band colors** (`prefill.csl:83-87`, comm_pe 20 vs 3 hits).
    Integrated time-share the reduce/shuttle queues → more communication contention.

### Verification
11. **Numeric oracle.** Standalone decode (`host/oracle_fp16.py`,
    `numpy_oracle_logits`, per-step top-k overlap) and prefill
    (`host.oracle_prefill_fp16`, fp32-accumulate forward) verify against a
    reference. **Integrated ship NO oracle** — e2e prefill literally "Oracle
    comparison intentionally omitted in e2e for now" (`launch.py:3017`); only a
    decode top-k-invariant sanity check. → integrated runs are unverified; a
    numeric regression is invisible.

## What integrated ADD (not gaps)

- The integration itself: **e2e** = fused co-residence + on-chip KV relay (colors
  17/21); **pdSeparate** = PD-disaggregation + host-DRAM KV bridge (`kv_mux`
  egress / `kv_adaptor`+`kv_demux` ingress).
- **pdSeparate adds a spec-dec `draft` path** (`draft_len`, `test_sim_1x2blk_kv_draft2.json`,
  19 hits) that standalone lacks.

## Parity (NOT a gap)

- **On-chip sampling** (temperature / top-p / nucleus / categorical / seed) is
  fully present in all three (`ht_tail.csl`).
- **Single-pass prefill TSC timing** is retained in both integrated.

## Implications

- The integrated models are **integration prototypes**: they proved the fused /
  PD-disaggregated KV dataflow runs on hardware (e2e device PASS), but to become
  real deployments they must **re-absorb the standalone kernels** — multi-request/
  varlen/chunked serving, EOS, #12 softmax + #13 perf, tall layouts, and the
  oracles.
- Directly tied to earlier findings: standalone's **chunked prefill** is the fix
  for the pdSeparate long-context prompt cap ([[e2e-pdSeparate-device-validation]]),
  and standalone's **varlen multi-round KV ingress** is the machinery any
  cross-request KV-reuse/eviction policy needs
  ([[kv-cache-policy-tradeoffs]]) — neither exists in the integrated homes.

## Superseded for the integration target (2026-07-11, M0/S2)

**This gap list describes `origin/main` (`fcfc8c1`).** Upstream **PR #14** (WaferAGI
`b9ff52b`, "Real Qwen3 1_7B Serving", base `fcfc8c1`, **unmerged**) already closes gaps
**#1 (multi-round), #2 (varlen), #3 (chunked prefill), #4 (EOS), #8–9 (numerics), #11
(oracle + real HF weights)** *for the integrated e2e/pdSeparate homes* (verified on code).
pdSeparate's KV plumbing was **replaced** (old `kv_mux`/`kv_adaptor`/`kv_demux`/`relay.csl`
deleted → shared `kv_ingress_adaptor`/`kv_ingress_injector`). What remains unbuilt even on
PR #14: the **keyed retain-not-discard KV store** (the sole M0 residual gap). The standalone
kernels themselves are **still mock-weight** at pr14. Full delta + port contract in
[[pr14-real-serving-port-contract]].

Corrections to this note surfaced in that dig: **item #5's `kickoff_relay.csl` is NOT on the
KV egress path** (it relays the forward-start timing sentinel); the real egress chain is
`prefill.csl` (`start_kv_egress`) → `kv_egress_colmux.csl` (+ transparent `kv_fwd.csl`) → host
stream.

## Updates

### 2026-07-13 — KV-management-abstraction digs refine this to "two lineages, not three"

From the pre-S6 abstraction design session (5 read-only digs; detail in
`memory/inbox/2026-07-13-kv-management-abstraction-design.md` (drained into `memory/topics/s6a-decode-kv-retain.md`). Refinements to this note:

- **e2e and pdSeparate decode.csl are compute byte-identical in staging** (differ by 83 lines = a
  WIP TSC profiler) and share the same on-wafer `kv_ingress_phase` north-shift receiver. So their
  KV difference is **entirely off-chip** (host `kv_adaptor`/`kv_demux` feeder vs on-wafer relay
  wiring), not a decode-kernel difference. The "gap" in this note is really **standalone vs one
  frozen integrated lineage**, not three distinct kernels.
- **KV compute *structure* is genuinely shared across all three** (Le's premise confirmed):
  `process_kv`/attention-reads/`iter_num`·`step`-banks/RoPE/cache-alloc identical modulo naming.
  The real divergences are **numerics** (this note's items #8–9: fp32 softmax + fast rsqrt in
  standalone vs bf16 in integrated) and **lifecycle presence** (this note's #1: integrated has no
  multi-round loop / `round_reset` / re-arm).
- **Consequence for KV-reuse work:** retain has **nowhere to attach in integrated** until the
  multi-round lifecycle is ported — that port ≈ the S4/S5 work (cluster-gated), so retain migration
  is NOT mechanical, and "abstract now, all inherit retain" is unavailable. Decision: S6 stays
  **standalone-first + seam-isolated**, extraction deferred to S4/S5.
- **Prefill also has a persistent resident cache + serve loop** (`K_cache_bank`/`V_cache_bank`,
  `enter_request` counter-only reset) — so **prefill retain is the same mechanism as decode retain**
  (MODERATE effort: `start_chunk` warm-start). S6 broadened to cover both kernels (S6a).

## Last updated

2026-07-13 (added the two-lineages / KV-abstraction refinement; prior: 2026-07-11 PR #14 supersession + kickoff_relay correction).
