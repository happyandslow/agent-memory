# Force-decode zero-seed deadlock — 2026-08-04

**Project:** WaferEngine-staging
**Author:** claude
**Status:** drained   <!-- drained 2026-08-06 into topic force-decode-startup-depends-on-prefix.md § Updates + plan.md -->

## What happened / finding

- Situation: while adding cache-hit resume to the standalone decode path, an exact resident-history
  hit appears to permit `F = prompt_len - start = 0`, so the host would send no forced token before
  free decode.
- Source audit shows that this is not a supported S6b boundary. In
  `models/qwen3_1p7b-decode/src/ht_head.csl:297-312`, HT_head consumes the host step-0 X only when
  `ht_step < F`. With `F=0`, it instead waits for HT_tail's sampled token. HTtail cannot produce that
  token until decode first receives X, so the dependencies close before step 0. Current host code
  still prepares a step-0 buffer, but HT_head takes the branch that does not consume it.
- M1 therefore keeps a mandatory known seed. Its safe match is
  `L_resume = floor(min(LCP, valid_len, prompt_len - 1) / P_BLOCK_SIZE) * P_BLOCK_SIZE`, followed by
  D9's `start = min(L_resume)` across lanes and the fail-closed guard
  `1 <= F = prompt_len - start <= decode_len`. An exact resident-history reuse request includes the
  known next seed and runs at `F=1`, not `F=0`.
- Evidence is source/control-flow only; no `F=0` simulation was run. Supporting a seedless hit would
  require a distinct device protocol and liveness proof rather than a host-only S3 change.

## Implications / next actions

- [ ] Add the shared host/config guard before enabling automatic M1-S3 hit scheduling.
- [ ] If an API later requires seedless reuse, scope it as a device feature and test the step-0
  color/dependency balance explicitly.

## Pointers

- `/home/lexu/WaferEngine-staging/milestones/M1-intra-pe-reuse.md` § S3.0 and Verification log
- `/home/lexu/WaferEngine-staging/milestones/kv-reuse-tradeoff-register.md` D11
- `/home/lexu/WaferEngine-staging/PROGRESS.md` Failed approaches
