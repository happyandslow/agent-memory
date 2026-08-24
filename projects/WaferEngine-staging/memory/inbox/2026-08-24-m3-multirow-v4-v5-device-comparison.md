# M3 multi-row storage: v4 GO-chain vs v5 cascade, three-way device verdict — 2026-08-24

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured

## Situation this applies to

Choosing the multi-row storage-strip design for M3 KV parking; estimating
its cost for any (R, E, mode); or extending either implementation. Full
record: `column_cycle_demo_multirow_v5/results/PREREGISTRATION-multirow.md`
(work repo) + ContextBase "M3 park/reload as-built performance model" page
(2026-08-23/24 update sections). 81 device runs (45 v5 + 36 v4), EPCC
CS-3, N=256, n=3/cell, EVERY cell 0-cycle spread, zero infra failures.

## The two implementations

- **v4 GO-chain** (`column_cycle_demo_multirow_v4`): R bands top-down,
  band k ↔ storage row k (far↔shallow), sequential epochs chained fully
  on-chip by a dedicated GO color (tap-and-forward south; band top emits
  GO(k+1) after its own completion = causal fence). Roles reprogrammed at
  GO taps via DIRECT switch-position byte writes (byte = in_sel<<5 |
  out_bits; S→RAMP=0x50, S→N=0x48; pos1=reg0[7:0], pos2/3=reg1[7:0]/
  [15:8]) — the tile_config `set_rxtx_switch_pos` library writes the
  wrong tx bit for RAMP (0x48 instead of 0x50; register-dump proven).
  First silicon 2026-08-23: everything works at 256 PEs.
- **v5 cascade** (`column_cycle_demo_multirow_v5`): compute column
  byte-identical to single-row v3; row 0 keeps the nearest band and
  store-and-forwards deeper words down strip-internal hop colors (all
  static routes); STRIP_TAIL word rides the same hop color as the causal
  end-of-stream; reload returns up mirrored hop colors, each row playing
  its own block before relaying (task atomicity + per-OQ FIFO = global
  owner order); row 0 synthesizes TURNs/fence. R ≤ 8 (hop-color budget).

## The verdict (device-fit models, `perf_model.py --selftest`, 39 anchors)

Both designs obey the SAME law: delta vs their own R=1 baseline is linear
in `fwd_words = (N−N/R)·E`. The coefficient is the mechanism:

    tax_v4 = 1.06 (task) / 1.29 (dsd) cyc/word   — router transit, ~wire speed
    tax_v5 = 30.7 / 47.0 (+157k const, dsd R>1)  — CE store-and-forward

25–35× apart. But each design pays its own ALWAYS-ON R=1 premium over v3:
v4 +≈9.6 cyc/word (role machinery), v5 +≈1.6 (cascade branches).
**Crossover: v3/v5 win single-row; v4 wins outright for all R ≥ 2**
(dsd E=512 R=4: v4 30% faster than v5). Open design: a hybrid (v4's
router transit + v5's static compute column) would dominate both.

## Why: durable lessons

1. **Each implementation carries its own baseline.** H1 falsified: v5's
   R=1 sits +0.7–2.3% above v3 (per-word branches don't compile out even
   when comptime-decidable); v4's R=1 is +8–11%. NEVER diff a new
   implementation against another implementation's anchors — always
   measure its own R=1/degenerate case in the same matrix.
2. **CE-touch vs router-touch is the ~30–75 cyc/word vs ~1–2 cyc/word
   dichotomy** on WSE-3, now measured four independent ways
   (c_park_storage 43.3, c_fwd_word 75.4, C_EMIT_LOOP 13, tax_v4 ~1.1).
   Any design that puts a CE data-task on the per-word path pays tens of
   cycles per word; anything router-level is nearly free.
3. **Preregistered bands get falsified usefully**: c_fwd_word 75.4 landed
   ABOVE [45,70] (forwarding = a full extra task dispatch, not an emit
   increment); v4's "per-epoch constant" H2 shape was wrong (its delta is
   ALSO per-forwarded-word, just router-priced). Both misses sharpened
   the model rather than embarrassing it — write the bands down first.
4. **dsd exposes serialization that task mode hides**: v5's strip rows
   emit their own block before relaying; with fast owners this surfaces
   as an E-independent ≈157k-cycle constant that the linear form needed
   added. Same family as the "backpressure-coupled span" trap (Exp-C).

## Pointers

- Models + 39 anchors: `column_cycle_demo_multirow_v5/perf_model.py`
  (predict / predict_v4_gochain / predict_v5_cascade, three selftests).
- Data: `.../column_cycle_demo_multirow_v5/results/2026-08-23-multirow/`,
  `.../column_cycle_demo_multirow_v4/results/2026-08-23-v4-matrix/`
  (v4 meta says git-commit "2ffe1f6" — placeholder; true commit b03bd6c).
- v4 metric is epoch_sum (excludes inter-epoch GO gaps ~2·bh cyc).
