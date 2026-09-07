# Capture: thin-block per-layer time is strongly sublinear in PE count (2026-09-06)

Source: session 4b-wide-layer, report Round 73–75
(docs/reports/2026-09-04-4b-wide-layer-session-report.md).

- Measured on CS-3 (2K context, one layer, strips 256 wide × 32 tall,
  appliance-compiled, cycles canonical, 750 MHz): cut (i) ATTN 32 | FFN 32
  production 17,589 cycles/token (42.6K tok/s rig rate); strip busy
  periods ATTN 17,520, FFN 13,768. Full-square (256²) per-layer times are
  11,886 / 5,802. So 1/8 of the PEs costs 1.48× (ATTN) and 2.37× (FFN)
  per layer — neither flat nor linear; T ∝ PEs^−α, α ≈ 0.19 (ATTN),
  0.41 (FFN). Throughput per allocated PE 5.4× better than the full square.
- Binding trade-off moves from SRAM to the i8 KV DSD stride cap:
  kv_len_per_pe ≤ 127 → context ≤ 127·H (4K at H = 32, 8K at 64, 16K at
  128; 29K today at 256).
- Enabler: the sub-height generator (funnels, per-axis trees, active_rows
  guard). The device wedge of the first sub-height run was phantom strip
  cells beyond the active height overwriting host-painted transit routes
  (fold parameter shrunk, region height not) — see the landmine memory.
- Height ladder complete (jobs 21–24, one layer, 2K, production, cycles/
  token): 256|256 11,866; 128|128 12,278 (ATTN 11,720 / FFN 11,696);
  64|64 13,658 (13,296 / 10,504); 32|32 17,589 (17,520 / 13,768). ATTN
  paces every height; per-PE efficiency 0.48 → 0.93 → 1.68 → 2.60
  tok/s/PE.
- One-lane ladder (256-wide blocks; a lane = 512 cols + HT, only one fits
  762): layers per block = H/32 → H = 128/L = 4 ≈ 15K tok/s @16K ctx;
  H = 64/L = 2 ≈ 27K @8K; H = 32/L = 1 ≈ 43K @4K; today 7.4K @29K —
  nearly constant tok/s × context (≈ 200M). Lifting the 127-position KV
  stride cap is the lever that would break the trade.
- L = 4 deployed and measured (09-06): 9 rows × (ATTN 256×128 + FFN
  256×128), 4 layers/block, 18 stages, one lane, odd-row serpentine +
  funnel column. Production forced 2K: 48,872 cycles/token = 15,346 tok/s
  @750 MHz = 2.08× today's A (101,670); prediction 4 × 12,278 = 49,112
  (0.995×). Gate: final record bitwise = free ref. Probe per-layer ATTN
  13,018 / FFN 6,024 — no multi-layer (weight-bank) penalty. Appliance
  SRAM 2K: ATTN 31.2 / FFN 27.8 / tail 43.4 KB; 8K: 35.7 / 27.8 / 44.8.
  Tree: /home/lexu/build/4b-l4/code/bprime-snapshot + l4.patch;
  docs demo/qwen3-4b-thin-stage/l4/.
- L = 4 at 8K: 62,198 cycles/token = 12,058 tok/s (1.91× A's 118,554);
  context slope 2.2 cyc/ctx-token (A: 2.8); probe ATTN 17,665 / FFN
  6,027. Program complete: 4 device + 2 compile jobs, no anomalies.
- L = 2 one lane (18 rows × 256×64, 2 layers, 36 stages) MEASURED:
  27,348 cycles/token = 27,424 tok/s @750 MHz = 3.72× A; prediction
  2 × 13,658 = 27,316 (1.001×). Gate: final record args+vals bitwise =
  free ref. wsjobs L2F wsjob-anlkis2hlrjgrl3dkvumjg, L2P
  wsjob-y6j5dsywfuoutq7yrsequv. Ctx cap 8,128.
- Deployable ladder measured on silicon: A 7,377 tok/s @29K ctx; L = 4
  15,346 @16K; L = 2 27,424 @8K; L = 1 rig point 42,641 @4K. tok/s ×
  context ≈ 215–249M across all rungs → rung choice is a context
  decision, not a performance one, until the 127-position KV stride cap
  is lifted (~10 lines, byte-identical by construction).
- L = 1 (36 rows × 256×32, 72 stages) MEASURED: 17,771 cycles/token =
  42,203 tok/s = 5.72× A; gate bitwise vs free ref; ctx cap 4,064.
  Compiled SRAM: ATTN 33.1 / FFN 28.2 / tail 43.4 KB.
- Oracle verdicts 32/64/128 rows all PASS, 0 defects over 3,000 steps.
- **Le's verdict (2026-09-06):** thinning L is a benchmark axis, not a
  deployment axis — for fixed context the per-PE KV is ctx ÷ block
  height, so halving height doubles per-PE KV (8K needs 64 positions/PE
  at H=128, 256 at H=32). The L axis converts context into stages; it
  does not create throughput (tok/s × context ≈ 172–249M across all four
  rungs). The sustainable axis is splitting the OPERATIONS, because only
  the score/scan step holds KV: cut (iii) A1|scan|O-proj|F1|F2
  multiplies stages while the KV stage keeps its geometry.
- Blocker for that branch: cut (ii)'s A1 stall — 128,131 cycles/token vs
  8,434 derived, localised to A1's first half (RMSNorm + QKV matvecs +
  fused QKV column all-reduce over 256 rows), 151.5K on 5 of 6 steps,
  true content 8.1K. Queue-7 theory falsified. Tool for it: the
  stop-and-read-counters frontier probe.
- **Vertical role stacking (2026-09-06)**: ATTN above FFN in ONE block
  column so their heights can differ; attention takes rows from the FFN
  and the context cap (127 × attention rows) rises. Runs end to end in
  sim at six bands / three layers with unequal heights; real config
  compiles on the appliance (wsjob-fbzg6xly3yqk3lom4buuob). Key enabler
  found by the subagent: change the K-pipe fold from CYCLIC (pipe = row
  mod 8) to BLOCK (pipe = row ÷ M) — then pipe k always carries the same
  contiguous dim slice regardless of band height, so a height-to-height
  hand-off needs no reshard and no extra hop. Strip machinery otherwise
  unchanged. Appliance SRAM: ATTN band 256×128 = 25.5 KB/PE, FFN band
  256×64 = 19.4, tail 43.4 (binding). At 128 attention rows the KV is
  256 B/PE at 2K and only ~2 KB at the 16,256 stride ceiling — so the
  ceiling is the stride field, not SRAM.
- **Vertical stacking MEASURED on silicon (2026-09-06)**: six bands
  ATTN 256×128 / FFN 256×64, 576 rows, one lane, 3 layers, 2K.
  Production 12,201.9 cycles/token (wsjob-p2cjfcwwtsuf9xwy9vveb7); gate =
  final-record top-k args and values bitwise equal to the free ref's last
  step. Probe: attention stage 11,568 vs the ladder's 11,720 for the same
  block (−1.3%, so standing a block in its own column costs its compute
  nothing); period 12,202 = pacing stage +4.1% (the K-pipe hop replacing
  the intra-row multicast); FFN 7,312 vs ladder 6,429 (+13.7%, the same
  hop, not binding — still under 2/3 of the pacing stage).
- **Second lane worth 1.34×**: per-layer cost 12,202 stacked vs 12,218
  inside an L=4 block, so stacking costs nothing per layer; two stacked
  lanes = 12 stages × 3 layers ≈ 36,606 cycles/token ≈ 20,489 tok/s at
  the same 589,824 PEs and the same 16,256 context cap, against L=4's
  measured 48,872 / 15,346. Two stacked lanes are 670 of 762 columns.
  Assumptions: flat-per-layer for MULTI-layer stacked bands (unvalidated),
  and the lane-to-lane riser costing less than the period.
- Landmines: `funnel_pe.csl` at G = 1 stalls one row silently (every cell
  is an owner, yet the gather still pushes and pops a lane that cannot
  arrive); a probe lane must never be the collector row's westmost cell
  (the host port drains from the east, so lane 0 does not feed it) — the
  cross-band-transit diagnosis for that one was REFUTED by bisect.
- **KV stride cap LIFTED and confirmed on silicon (2026-09-07)**: the one
  strided K-cache descriptor in `process_kv` became `kv_cols` scalar
  stores (~10 lines, `demo/qwen3-4b-thin-stage/kv-stride-lift.md`).
  Gate: 1,000 device records byte-identical on both the free and forced
  paths (S1F/S1P vs L1F/L1P). Cost +0.05% (17,780 vs 17,771 cyc/token).
  Negative control exact: unpatched refuses to compile at
  kv_len_per_pe 136 with "integer value '136' cannot be coerced to type
  'i8'" on decode.csl:1378; patched runs. There was NO launcher assert —
  the cap was enforced solely by the CSL cast.
  **L = 1 ceiling 4,064 → 12,032 (2.96×)**, pinned (12,064 fails on PE
  memory). Measured growth 47.9 B per position per PE.
- Ceiling model, calibrated and then validated (predicted 11,520 vs
  measured 12,032): per-PE context bytes = 16 × (context ÷ rows) ×
  (L + 2) — 16 B K+V per layer, 16 B f32 score slice and 16 B unnamed,
  both shared across layers. Post-lift ceilings by model, each still
  needing its own compile: L = 2 ≈ 17,400, L = 4 ≈ 23,600, A unchanged
  ≈ 30,200 (A was already SRAM-bound), stacked ATTN 128 ≈ 28,300.
- Method note worth keeping: per-token cost tracks the LIVE context
  (`iter_num`), not MAX_SEQ_LEN, so a capacity sweep must size each
  point's prefill to its context or it measures nothing.
- Pending: the A1 stall; vstack second lane (Le's decision); the 128²
  two-lane family (width axis) scoped only.
