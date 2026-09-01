# U1/U2 benchmark-axis legality gotchas — 2026-09-01

**Project:** wse3-performance-model
**Author:** claude
**Status:** captured

## What happened / finding

Situation: designing a benchmark matrix over nominal axes (geometry, batch,
active KV, mechanism, rows, separation) from a frozen implementation, and
assuming that a point the generator "accepts" is a point that can be
measured as intended. A read-only source audit (4B worktree `93a6d0e`,
WaferEngine `fcfc8c1`, offload head `255dab72`) found four traps that a
nominal Cartesian product hides:

- **A timing window is not a KV point.** Both Qwen decode generators append
  one token per counted step and never re-seed inside the window: the 4B
  per-token TSC averages over `DECODE_LENS - WARMUP - 1` tokens, and the 1.7B
  bench averages over `MAX_OUTPUT_LEN - WARMUP = 48` rounds. "Active KV =
  seed + 1" is exact only for the first counted token. Symptom: two KV levels
  chosen at design time, but every observation actually spans
  `[seed + warmup + 2, seed + decode_len]`. Fix in the design: freeze a short
  counted window (proposed `W=8`, `WARMUP=2`) and bind the window, not a
  point, as the model input.
- **A metric boundary can be missing even at the exact anchor.** The 4B role
  images contain no TSC at all; the only device timing is one end-to-end
  per-token window on an HT_tail PE. So `attention_role_cycles` /
  `ffn_role_cycles` are an instrumentation gap even for the canonical
  `256x256` deployment, and the first 4B rows are parent-boundary
  observations. By contrast the 1.7B bench emits twelve per-segment sums, and
  Attention = segments 0-6, FFN = 7-11 are exact post-hoc boundaries with no
  source change.
- **Generator coverage is not config coverage.** The 1.7B rectangular bench
  accepts any `X`, `Y`, but the `256x256` bench config at `fcfc8c1` is a
  dangling symlink whose target file is gone; only `128x128` and `256x128`
  have real config files, and no config has `X < Y`. Check `git ls-tree`
  modes (`120000`) and `cat-file -e` on symlink targets before calling a
  geometry "tracked".
- **U2 axes are per-mechanism.** v4 accepts `--distance` in its sweep driver
  but never passes it on (storage is placed at `PLACE_Y + N` unconditionally),
  so `D` is metadata, not an axis, for v4. v4 has no full-cycle metric and no
  cross-PE clock alignment, so `epoch_sum` is comparable with v3/v5
  `p0_full_cycle` only at `R=1`. `R` must divide `N`, so `R=3` is illegal at
  `N in {128, 256}`. Repetitions are separate jobs, one cycle each, no re-arm.

## Implications / next actions

- [ ] Before freezing any benchmark row, verify three things separately: a
  tracked config binds the point, the metric boundary exists in the image,
  and the timing window holds the workload axis fixed (or record the window).
- [ ] Le decides D1-D13 in
  `docs/plans/2026-09-01-u1-u2-experiment-matrix-selection.md` before the S3
  manifests freeze rows.

This is partly procedural (the three-part check above) and may deserve
promotion to a benchmark-design skill if it recurs on another model family.

## Pointers

- `/home/lexu/wse3-performance-model/docs/plans/2026-09-01-u1-u2-experiment-matrix-selection.md` (Section 2, F1-F14)
- `4B@93a6d0e:models/qwen3_4b-decode/launch.py:234-238,2569-2598`; `src/ht_tail.csl:1262-1265,1345-1355`
- `WE@fcfc8c1:models/qwen3_1p7b-decode/bench/layer_block_rec/launch.py:52-53,151-179`; `src/decode.csl:938-940,1198-1265`
- `WE@255dab72:models/qwen3_1p7b-decode/bench/m3_park_band/column_cycle_demo_multirow_v4/launch.py:117,176-186`; `sweep_device.py:44-46,117-122`
