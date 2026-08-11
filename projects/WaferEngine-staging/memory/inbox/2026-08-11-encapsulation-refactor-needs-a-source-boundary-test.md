# An encapsulation refactor is undone by a test-only mutable seam — 2026-08-11

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured

## Situation / finding

The whole point of the cleanup was to fold `KVStore` into `RoundPlanner` as
genuinely *private* state so `launch.py` stops coordinating it as a peer — i.e.
close an ownership boundary. The implementation passed all 410 host tests and
looked done. An independent review still flagged it: the refactor had kept a
public `RoundPlanner.store` property returning the mutable `KVStore`, and the
result carrier `RuntimeExecution` exposed the whole mutable controller "merely
for tests." Both re-open the exact boundary the refactor was supposed to close —
a passing test suite does not detect this, because the tests are what the escape
hatch exists for.

What actually enforces the boundary:

1. Keep the field private (`self._kv_store`). Low-level unit tests may
   white-box **inject** the private field; production / calling-flow tests must
   not hold a mutable handle.
2. Have the result carrier expose only an **immutable projection** — here a
   `SlotSnapshot` tuple via `evidence.final_kv_snapshot`. Tests derive what they
   need (owner, per-PE length, sequence→slot) from that snapshot, not from a
   live object.
3. Add a **source-boundary regression test** that asserts, against the source
   itself, that production code has no forbidden import / construction / direct
   mutation call and that the result dataclass carries only the immutable field
   (`RuntimeExecution.__dataclass_fields__ == {"evidence"}`). This is what makes
   the boundary hold under future edits, where behavioural tests would still pass.

Procedural and recurring: any "fold peer component X into owner Y as private
state" refactor has this failure mode, and the fix is the same three moves.

## Implications / next actions

- [ ] When a refactor's goal is encapsulation (not behaviour), add a
      source-boundary regression test as part of the same change — don't rely on
      the behavioural suite to prove the boundary.
- [ ] Consider promotion: this is altitude-general (states without naming the
      specific bug) and would recur across projects — candidate for a review skill.

## Pointers

- `models/qwen3_1p7b-decode/round_planner.py`, `launch.py`,
  `tests/test_round_input_launch_order.py` (`ControllerOwnershipBoundary`)
- Branch `lexu/staging/m1-inner-pe-reuse`; final gate 414 host tests
  (410 baseline + 4 boundary regressions)
- Related process contract: `inbox/2026-08-04-m1-s3-planner-implementation-review-contract.md`
