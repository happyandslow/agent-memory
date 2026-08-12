---
summary: Encapsulation refactors need immutable test projections and source-boundary regression checks; test-only mutable seams can reopen the ownership boundary while behavioural tests still pass.
tags: [WaferEngine-staging, encapsulation, refactor, source-boundary, tests, review, drained-inbox, 2026-08-11]
---

# Encapsulation refactors need source-boundary tests — 2026-08-11

The M1 inner-PE-reuse cleanup folded `KVStore` into `RoundPlanner` as private state so `launch.py` no longer coordinated it as a peer. The implementation passed the host suite, but review still found two test-only escape hatches that reopened the same boundary: a public `RoundPlanner.store` property returning the mutable `KVStore`, and a `RuntimeExecution` result carrier exposing the mutable controller for tests.

The boundary held only after three changes:

1. Keep the owner field private (`self._kv_store`). Low-level unit tests may white-box inject the private field; production/calling-flow tests must not hold a mutable handle.
2. Expose only an immutable projection from the result carrier. In this case, `evidence.final_kv_snapshot` returns `SlotSnapshot` tuples, and tests derive owner, per-PE length, and sequence→slot facts from that snapshot rather than from a live object.
3. Add a source-boundary regression test that asserts production code has no forbidden import, construction, or direct mutation call and that the result dataclass carries only immutable evidence (`RuntimeExecution.__dataclass_fields__ == {"evidence"}`).

Durable lesson: when a refactor's stated goal is ownership/encapsulation rather than behaviour, the behavioural suite cannot prove the boundary. Add a source-level boundary test in the same change.

## Pointers

- Branch: `lexu/staging/m1-inner-pe-reuse`
- Files: `models/qwen3_1p7b-decode/round_planner.py`, `launch.py`, `tests/test_round_input_launch_order.py` (`ControllerOwnershipBoundary`)
- Gate: 414 host tests (410 baseline + 4 boundary regressions)
- Source capture: `memory/inbox/2026-08-11-encapsulation-refactor-needs-a-source-boundary-test.md`