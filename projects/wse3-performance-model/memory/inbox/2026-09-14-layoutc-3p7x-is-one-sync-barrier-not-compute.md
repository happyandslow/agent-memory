# A shrunk multi-stage layout is 3.7× slower and no stage's arithmetic explains it — 2026-09-14

**Project:** wse3-performance-model
**Author:** claude
**Status:** captured

## What happened / finding

Situation: layout C (Qwen3-4B decoder layer as three thin stages A1 128×80 QKV /
A2 128×256 attn+O / A3 128×160 FFN, all 128-wide) measured 3.73–3.89× the
original two-block layer's serial single-layer latency on CS-3
(`inbox/2026-09-13-layoutc-single-layer-area-latency.md` — "no bottleneck was
localized"). Two wrong explanations were tried before the right one:

- **Per-PE MAC count does NOT predict stage time in this kernel — refuted twice.**
  It named the pacing stage backwards (says FFN 2× ATTN in FLOPs; measured
  T_attn/T_ffn = 2.05 at 2K, ≈2.7 at 8K — ATTN paces and grows with context, FFN
  is flat and idles 51–63 % in a split). 4b-wide-layer's height ladder: halving a
  block's rows doubles per-PE MACs and moves time −1.4 % (ATTN) / +4.3 % (FFN).
  The kernel is comm/latency-bound per participant, not FLOP-bound.
- **Per-stage TSC on CS-3 (5 jobs, closure ≤0.03 %/PE, perturbation <0.5 %,
  delay control lands only in waits, context slope 0.47 cyc/pos isolates to A2)
  localized the 76.3K-cycle gap:** attn+O compute **0.91–0.96× — not degraded at
  128-wide**; QKV 1.22–1.35×; FFN 1.51×; X/Z redistribution data movement <1 %;
  **one synchronization point, A2's `round_barrier` (`decode.csl:414-416`),
  35,536 cyc per token = 46.6 % of the gap, identical at both contexts.**
- Mechanism (source + segments; the cascade's per-row finish times were NOT
  instrumented, so this part is an interpretation): only A2's edge column x=0
  reshards X 32/row→10/row by a **vertical cascade through 256 CEs**
  (store-and-forward, `@fmovh(atom_out, atom_in)`), borrowing collective queue
  IQ3/OQ3 via flush+rebind (colour 0→12/13→0, three rebinds per token), then a
  row multicast east. The barrier is a normal 2-phase tree (group 16; a Y
  all-reduce over the same 256 rows costs ~830 cyc elsewhere) — the 35.5K is the
  top PE waiting for the cascade to reach row 255; interior PEs book the same
  wall window as `x_row_recv` 35,175. My "256 × 139 serial chain" fit of the
  barrier itself was **internally consistent and wrong** (source: tree).
  *Refined same day from `tall_stage.csl:155-172`:* the cascade volume is
  row-dependent — row y<80 forwards 22·(y+1) elements, rows 80..255 forward
  2560−10·(y+1); **rows 79/80 relay ~1,760 elements = ~880 two-element CE
  atom ops each**, while the instrumented row 0 forwards 11. 35,536 / 885 ≈
  40 cyc/atom ≈ 20 cyc/word, the relay-constant class. Working hypothesis
  (no control yet): the barrier wait is the cascade's *volume* at its widest
  rows through the CE, not its depth; "redistribution < 1 %" was a row-0
  instrument reading. Check: instrument edge rows 80/255, or an extent-2
  relay microbench. Fix shape if it holds: bigger atoms / router
  pass-through / an A1 height that divides A2's (depth 4 instead of 256).
- **First measured width-axis compute data:** a narrow block costs **context,
  not time** — per-PE KV doubles at 128-wide (definitional), attention time ≈
  unchanged. Non-monotonic near ½ on both axes (shallow minimum at half).

## Implications / next actions

- Layout C is **closed** as a performance direction (Le, 2026-09-13); the
  shortfall is an engineering artefact (one full-column sync a different phase
  design need not have), not "the width axis is expensive". Fixes if ever
  revisited: reshard on every column in parallel; cascade via router forwarding
  (~2 cyc/hop) not CE store-and-forward (~13 cyc/word class); scope the
  barrier to rows touching resharded X; or avoid resharding entirely (fusion).
- [ ] To confirm the cascade reading: instrument edge-column row 255's
  `redistribute_x` end time vs row 0's (one extra CS-3 job, same harness).
- Do not price any stage of this kernel from FLOPs; use measured per-slot
  cycles (`topics/qwen3-4b-cs3-measurements.md`).

## Pointers

- `docs/reports/2026-09-14-tall-per-stage-timing.md` (+ evidence JSON, repro
  tgz; jobs wsjob-y3tdianwmtbxzbefctwkmj / -s6grwwgxdopc98juozffab /
  -mddtxvoecf2dgnbqwbpbmv / -gc6zqrqbwpc33gflv34qe6, delay -kqmrjddcjwarwoywnkegvv)
- `docs/reports/2026-09-13-layoutC-performance-conclusion.md` §5b (pacing,
  height ladder, width penalty), §3 (per-stage table, correction banner)
- `docs/diagrams/2026-09-14-layoutC-a2-sync-timesteps.png` (t0–t7 of the reshard)
- `docs/reports/2026-09-13-attn-vs-ffn-three-axes.png` (FLOP vs TIME vs SRAM)
