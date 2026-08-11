# M1 implementation steps require a device gate — 2026-08-10

**Project:** WaferEngine-staging
**Author:** human
**Status:** drained
**Drained to:** `memory/topics/m1-s37-prefix-reuse-device-gates.md` (2026-08-11)

## What happened / finding

- While reviewing M1/S3.6, the local simulator attempt was not a conclusive execution gate: its nominal "2x2" geometry meant 2x2 blocks of 8x8 PEs, it ran two rounds instead of the one-round red case, and it timed out before producing a verdict.
- Le explicitly set the workflow policy that, beginning with the next implementation step (currently S3.7), every step must be exercised on the device. Host tests, mocks, compilation, and simulator results are earlier diagnostic layers and do not replace a device verdict.

## Implications / next actions

- [ ] Before implementing each step, define its minimal, step-specific device config, expected evidence, pass/fail gate, and bounded runtime.
- [ ] After implementation and host checks, run the exact device gate and preserve the config, logs, artifact identity, and machine-readable verdict for review.
- [ ] Do not mark a step complete or hand it off as passed without the device result. If device access or execution is unavailable, keep the step explicitly incomplete/blocked rather than substituting simulator evidence.
- [ ] Continue stopping for Le's review at each agreed step boundary only after reporting the device evidence or the explicit device blocker.

## Pointers

- `/home/lexu/WaferEngine-staging/milestones/M1-intra-pe-reuse.md`
- `/home/lexu/WaferEngine-staging/models/qwen3_1p7b-decode/`
