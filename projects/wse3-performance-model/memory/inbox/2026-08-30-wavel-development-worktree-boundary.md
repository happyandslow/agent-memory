# Project development and WaferEngine evidence boundary — 2026-08-30

**Project:** wse3-performance-model
**Author:** codex
**Status:** captured   <!-- captured | drained -->

## Corrected decision

- `/home/lexu/wse3-performance-model` is the primary development repository for
  performance results and manifests, performance models, provider registries,
  and Wavel/KAIR plugins. The earlier interpretation that this project should
  move its main development into a WaferEngine worktree is superseded.
- `lexu/staging/kv-feature` identifies the current WaferEngine implementation
  version against which the project integrates; it is not this project's
  development base.
- The frozen offload-study evidence and the current WaferEngine implementation
  reference are separate read-only identities for M1. At
  `2026-08-30T11:58:14Z`, local and advertised remote refs were
  `m3-on-chip-kv-offload-study@255dab72c4231f85c28a82007bf4c2830696537d`
  and `kv-feature@f5252b3428cb0197e364beb2954457ed98467e2f`; they diverged
  after merge base `77d6d407328f46314c90238d799f9ed5402d55b6`.
- If a later task separately authorizes changes to WaferEngine product source,
  use a clean isolated WaferEngine worktree based on a freshly verified source
  ref. That conditional source-worktree rule does not relocate this project's
  main development.

## Implications

- M1-S1b inspected the frozen offload commit read-only through Git objects; it
  did not require or create a WaferEngine development worktree.
- Never substitute the offload-study head, `kv-feature`, and their historical
  merge base for one another.
- Project tracking and artifacts must describe `kv-feature` as an implementation
  reference, not as the future development base for wse3-performance-model.

## Pointers

- `/home/lexu/wse3-performance-model/ROADMAP.md`
- `/home/lexu/wse3-performance-model/PROGRESS.md`
- `/home/lexu/wse3-performance-model/milestones/M1-wavel-pipeline-placement-plan.md`
