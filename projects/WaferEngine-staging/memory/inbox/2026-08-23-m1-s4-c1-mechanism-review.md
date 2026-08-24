# M1-S4 C1 fixed-communication mechanism review — 2026-08-23

**Project:** WaferEngine-staging
**Author:** hermes
**Status:** captured

## What happened / finding

- When equal-prompt, P-aligned prefix hits differ by lane, a simple C1 can keep
  one global decode/RoPE position and rejoin lane `i` after the token-step delta
  `R_i - min(R)`. It does not need a per-lane RoPE cursor.
- At `bsz=2`, the minimum device threshold state is two `i16` rejoin deltas:
  four extra bytes per replicated metadata tile and four bytes of persistent
  state per decode PE. This is only a lower bound; lane-sliced DSDs, dummy
  buffers, and code can add SRAM and must be charged to M1-S5.
- The host change is not four bytes. Current `RoundPlan`, `KVStore`, and ledger
  commit all enforce one common retained length. Correct C1 needs per-lane
  retained/rejoin state, a preserve/no-truncate transition for longer hits,
  unequal matched-prefix ledger bases, and commit logic that ignores redundant
  forced inputs before a lane rejoins.
- Current decode work is mixed: some per-batch loops can be predicated, while
  zero/cast/residual/SiLU maps and every collective/transfer retain full
  `bsz * width` extent. Fixed-extent padding does not reduce communication
  bytes or wavelet counts. The avoidable local-compute fraction must be measured
  on CS-3 rather than assumed.
- Prefix masking and EOS masking remain separate. The first C1 mechanism should
  cover prefix rejoin only; EOS needs cross-region mask propagation and
  per-lane actual-length commit.
- Communication compaction is a later protocol using fixed segment widths plus
  a replicated runtime segment count/map. It is not minimal C1 and carries
  count-exactness/deadlock obligations.

## Implications / next actions

- [ ] Review C1-M: benchmark-only prefix thresholds, fixed communication, no
      production ledger publication until per-lane host semantics exist.
- [ ] If approved, run the 25-accepted-run `bsz=2` small gate before the
      conditional 85-run cost-surface matrix.
- [ ] Record all added mask/DSD/state SRAM in M1-S5; keep full-model `bsz=4`
      model/component-only because `ht_tail` fails SRAM at `bsz=3/4`.

## Pointers

- Historical review base: `77d6d407328f46314c90238d799f9ed5402d55b6`.
  Final pushed branch `lexu/staging/m1-ragged-execution-study` records the
  implementation at `4a4e6c3d11b8b77b835446cde507351141f95f6c` and the
  study/evidence tip at `a24beb4c6c3dcb4595dfd940fe5b8672ae9e1048`.
- `docs/analysis/m1-s4-c1-workload-step-review.md`
- `docs/analysis/m1-s4-ragged-execution-ab-study.md`
- `models/qwen3_1p7b-decode/round_plan.py`
- `models/qwen3_1p7b-decode/round_planner.py`
- `models/qwen3_1p7b-decode/src/decode.csl`
- Related topics: `mixed-hit-miss-batch-needs-no-ragged.md`,
  `m1-s37-prefix-reuse-device-gates.md`,
  `automatic-replacement-early-stop-fails-closed.md`
