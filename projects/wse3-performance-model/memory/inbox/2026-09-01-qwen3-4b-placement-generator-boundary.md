# Qwen3-4B placement-generator boundary — 2026-09-01

**Project:** wse3-performance-model
**Author:** codex
**Status:** captured

## What happened / finding

- A read-only audit of the clean detached Qwen worktree at
  `93a6d0e6986ac1cd91c8abc80fa9e0a032e13f52` found that the canonical
  role-split launcher does not expose independent Attention/FFN region-size or
  placement knobs. It requires two role columns, one shared square
  `P_BLOCK_SIZE`, and fixed derived placement origins.
- For `device_2x4_8k.json`, the device lower bound `P_BLOCK_SIZE >= 256` and
  `HT_WIDTH_tail=128 >= P_BLOCK_SIZE/2` force `P_BLOCK_SIZE=256`. The exact
  materializable role layout is four alternating rows of adjacent `256x256`
  Attention and FFN regions, nine layers per row.
- Same-row Attention/FFN edges use static east/west row multicast. Final
  FFN-to-next-row Attention edges use the separate eight-way K-pipe/strip
  implementation. The latter is not a generic vertical placement transport;
  vertical or diagonal same-layer placement has no matching generator.
- Current clean Wavel `main@9b5e88b3b3e8` can place fixed-footprint `MacroOp`
  objects and has atomic compute/collective generators, but it has no
  Attention-role or FFN-role generator. Its current MacroOp cost path uses an
  embedded estimate or child-estimate sum, not the proposed versioned provider
  contract.

## Implications / next actions

- [ ] Treat the current `256x256` alternating layout as the mandatory exact M2
  anchor; do not present arbitrary rectangles as existing materialization
  capability.
- [ ] Make a handwritten plan the first predictor consumer, independently of
  Wavel adoption. The plan queries Attention and FFN component models for their
  independently selected rectangle widths and heights, then queries a separate
  communication model using the exact source/destination regions, tensor
  layouts, physical relation, payload, and algorithm.
- [ ] Do not freeze region height in the provider contract. Holding height at
  256 is only a possible experiment-sampling tactic. Unequal source/destination
  heights require an explicit re-sharding communication template; if none is
  registered, component predictions may remain available but the complete plan
  estimate must fail closed rather than use bytes-and-distance fallback.
- [ ] Parameterize and validate bounded generators before measuring any
  non-canonical rectangle. Exact candidate dimensions and the first measurement
  matrix remain unconfirmed.

## Pointers

- `/home/lexu/worktrees/1.7b-pipeline-af/models/qwen3_4b-decode/launch.py:188-203,240-269,554-570,998-1123`
- `/home/lexu/worktrees/1.7b-pipeline-af/models/qwen3_4b-decode/src/decode.csl:1707-1727`
- `/home/lexu/worktrees/1.7b-pipeline-af/models/qwen3_4b-decode/src/decode_strip.csl:1-16`
- `/home/lexu/KAIR/Argus/wavel/src/wavel/ir/macro.py:17-56`
- `/home/lexu/KAIR/Argus/wavel/src/wavel/mapping/cost.py:220-226`
