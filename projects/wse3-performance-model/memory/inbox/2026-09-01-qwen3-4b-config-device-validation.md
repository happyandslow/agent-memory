# Qwen3-4B config pair device validation boundary — 2026-09-01

**Project:** wse3-performance-model
**Author:** codex
**Status:** captured

## What happened / finding

- When deciding whether the Qwen3-4B `device_2x4_8k` model config and
  `device_prefill4k` request config are suitable for an S3 canonical manifest,
  validate the exact checked-in bytes rather than a historical CS-3 copy. The
  historical remote copy was stale and omitted `DECODE_LENS`.
- The exact pair from WaferEngine source revision
  `93a6d0e6986ac1cd91c8abc80fa9e0a032e13f52`, subtree tree
  `7120f9085805f8702bd49cbda1f67f6d7e94ccd7`, was staged to an isolated CS-3
  directory. Worker-side SHA-256 matched the local files:
  `c522e48d616eafeac8ae081a342fa9f1496dd5ed977740378f0a83cfd203f67d`
  and `26dacfb4b1837143e0a1c80b04f4739c8e1e73b86e146d65b80f95e192b72e5c`.
- CS-3 job `wsjob-3ebi6bbgdtl2offccfzdjk` compiled, loaded, and completed the
  requested 4096-prefill/4096-decode device run. This establishes operational
  liveness for the exact source/config identity, not full numerical correctness:
  the device path skipped the slow NumPy oracle, and the one-round request did
  not exercise rearm identity.
- A prior identical submission failed during appliance artifact upload with an
  HTTP 503 before compilation; the successful retry shows that failure was a
  control-plane incident, not config or kernel evidence. The successful run
  also reported an appliance client/server semantic-version mismatch, which
  remains environment provenance.
- Le subsequently selected this exact source/config tuple as the canonical S3
  U1 role-split baseline input. This freezes implementation/config identity,
  not a performance witness, calibrated model, or complete benchmark manifest.

## Implications / next actions

- [x] Record the exact source/config tuple as the canonical S3 U1 baseline
  identity in the project milestone tracker.
- [ ] If S3 requires numerical or rearm correctness, add separate oracle and
  multi-round gates; do not promote diagnostic timing output into S2 model
  evidence.

## Pointers

- `/home/lexu/worktrees/1.7b-pipeline-af/models/qwen3_4b-decode`
- CS-3 log export for `wsjob-3ebi6bbgdtl2offccfzdjk`
- `/home/lexu/wse3-performance-model/milestones/M1-wavel-pipeline-placement-plan.md`
