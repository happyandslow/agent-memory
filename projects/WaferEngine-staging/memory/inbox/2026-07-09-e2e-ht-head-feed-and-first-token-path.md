# e2e HT_head feed colors, and the first-token path is NOT on-chip — 2026-07-09

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured

## What happened / finding

Session read `models/qwen3_1p7b-e2e` end to end (decode CSL directly; prefill +
`launch.py` via subagents) to answer "how is HT_head fed, and what colors carry
prefill's first token + KV cache into decode?"

**Correction to a working assumption.** Only the **KV cache** crosses from
prefill to decode on-chip. The **first token does not.** There is no fabric path
of any color from `pf_ht_tail` to decode's HT_head.

- Prefill's sampled first token exits south: `pf_ht_tail` → `pf_mux` →
  `pf["logits_stream"]` → **host** (`launch.py` `runtime.receive(pf_blob)`).
  It is read, printed, and never sent back to the device.
- Decode's step-0 input X is **host-computed**, not prefill's token:
  `launch.py:~3006-3028` builds `host_x_f16 = W_E_full[cfg["token_ids"]]`
  (`token_ids` defaults to `[0]*bsz`, seed-2024 mock W_E) and sends it as
  `x_step_buf_u32` on `x_stream` into decode's demux.
- So the two halves are fused in **KV state only**. Decode begins generating
  from a config-chosen token, unrelated to the token prefill just sampled. A
  true fused e2e continuation would need either a host hop or a new on-chip
  token wire from `pf_ht_tail` north into decode's HT_head.

**Decode HT_head feed colors** (ids from `launch.py:535-585`):

| Wire | Color id | From → To | When |
|---|---|---|---|
| `pre_embed_x_color` (`c1_color`) | **18** | host → `x_demux` → HT_head west edge | step 0 only |
| `tok_bcast_color` | **7** | decode `ht_tail` root row → HT_head bottom edge | steps 1+ |
| `post_embed_x_color` (`c2_color`) | **23** | HT_head diag PE → decode row_0 west | every step |
| `ht_ready_color` | **0** | HT_head col=0 → demux (1-hop barrier) | init |
| `UP_A/UP_B`, `DOWN_A/DOWN_B` | 21, 22, 8, 9 | HT_head internal W_E gather chain | steps 1+ |

HT_head at step 0 does **no** embedding lookup — it just drains the host's
pre-embedded X on c1 into `embed_buf`. From step 1 it does the real 2-phase
`W_E` gather driven by token ids arriving on color 7 from decode's own HT_tail.
`DOWN_A/DOWN_B` (8, 9) are **aliases of `kpipe_a/b_colors[3]`**.

**KV cache path, prefill → decode (colors 17 / 21):**

| Segment | Region | Code | Colors |
|---|---|---|---|
| A. gather + transform | prefill block region | `prefill.csl` `start_kv_transfer` / `kv_step` states 0-3; `comm_pe.csl` `kv_sweep`, `kv_col_emit`, `kv_paint_col_chain` | sweep W **18/19**, sweep E **20/22** |
| B. north shift | prefill → relay seam → decode | `comm_pe.csl` `kv_north_shift`; `relay.csl` (no tasks, `build_relay` paints SOUTH→NORTH transit) | **17 / 21** |
| C. decode ingress | decode block region | `decode.csl` `kv_ingress` / `kv_ingress_phase`; `comm_pe.csl` `kv_flush_then_init`, `kv_oq7_empty` | **17 / 21** on IQ7/OQ7, then rebound to `broadcast_color` (5) |

Parity: even fabric rows send on 21 / recv on 17; odd rows swap at runtime
(`kv_ingress` reads `get_fabric_coord(Y)`). Relay also reserves color **22** at
RAMP/RAMP with no traffic. 17 aliases a K-pipe id and 21 aliases `UP_A_color`;
`launch.py:576` asserts these only ever coexist at X-disjoint coordinates
(strips / HT band vs block columns).

**Two side findings:**

1. `standalone-vs-integrated-kernel-parity` is **partly stale**. e2e `decode.csl`
   is md5 `05cc76d4` (note pins `71d80bba`) and now HAS Qwen3 QK-Norm +
   fp32-accumulate GEMV (`@fmachs`). Serving gaps (multi-round `round_reset`,
   EOS `STOP_THRESHOLD`, runtime-varlen prefill, chunked prefill) still hold.
   One numerics gap survives: e2e decode `softmax_score` exponentiates in
   **bf16** (`@map(fast_exp, score_dsd, score_dsd)`), keeping only the
   denominator f32; standalone runs exp/sum/normalize fully in f32. Prefill's
   softmax IS full-f32.
2. `tools/csl_color_audit` **cannot currently audit e2e**, in both directions:
   default `--ref origin/main` raises ProbeError (the `test_sim_2x2blk_kv_prof*`
   configs are untracked), and `--worktree` raises CoverageError at
   `src/decode/decode.csl:1414` — the raw `@set_config` on
   `PERF_COUNTER_CONTROL` in `kv_prof_enable()`. The standalone decode kernel
   audits fine. This is the tool refusing rather than under-reporting.

## Implications / next actions

- [ ] Decide whether fused e2e should carry prefill's first token to decode
      on-chip (new wire `pf_ht_tail` → decode HT_head), or whether the host hop
      is acceptable. Today decode's output is not a continuation of prefill's
      prompt — relevant to any end-to-end accuracy claim.
- [ ] Teach `tools/csl_color_audit/parse_csl.py` the raw `@set_config(addr/word_size, val)`
      form so the KV-profiler code is covered; do NOT widen `_TRIPWIRE_BENIGN`.
- [ ] Update `standalone-vs-integrated-kernel-parity` at the next maintain pass:
      the numerics half of the gap is mostly closed; record the bf16-exp residue.

## Pointers

- `models/qwen3_1p7b-e2e/launch.py:535-585` (decode color ids), `:921-953`
  (HT_head ports), `:2026-2036` (connects), `:2863-2878` (`build_relay`),
  `:3006-3028` (host X seed).
- `models/qwen3_1p7b-e2e/src/decode/ht_head.csl`, `decode.csl:1424-1463`
  (`kv_ingress`), `src/prefill/prefill.csl:805-845` (`kv_step`).
- Topology reference (other session, unverified but consistent with code):
  `assets/prefill-decode-transfer/e2e-topology-full.svg`.
- Relates to [[prefill-decode-transfer-bandwidth]] (A/B/C segments),
  [[standalone-vs-integrated-kernel-parity]].
