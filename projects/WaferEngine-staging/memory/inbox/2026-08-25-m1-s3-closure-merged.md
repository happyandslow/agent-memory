---
summary: M1-S3 closed after PR #5 merged controller ownership cleanup and the post-cleanup host/device gates passed.
tags: [WaferEngine-staging, M1, S3, closure, kv-reuse, device-gate, cs3, 2026-08-25]
status: drained 2026-08-25 into memory/topics/m1-s37-prefix-reuse-device-gates.md and plan.md
---

# M1-S3 closure merged — 2026-08-25

- PR #5 merged the remaining closure artifacts into `lexu/staging/kv-feature@f5252b3`; PR #4 had
  supplied the feature body.
- `RoundPlanner` privately owns `KVStore`. Launch enters through controller planning, start-action,
  success-commit, and immutable-snapshot seams; it does not coordinate a peer store.
- The full post-cleanup host suite passed 414 tests.
- The real CS-3 closure gate reproduced the tracked two-round miss→positive-prefix case:
  `start/F = 0/16 → 8/9`, both final 24-token ledgers reconstructed `OK`, launcher `rc=0`, and no
  job remained.
- Therefore M1-S3 is complete. Ragged execution, capacity, and the mixed end-to-end matrix remain
  M1-S4, S5, and S6 respectively; they are not S3 blockers.
