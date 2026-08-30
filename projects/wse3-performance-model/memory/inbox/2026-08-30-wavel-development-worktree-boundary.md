# Wavel development worktree boundary — 2026-08-30

**Project:** wse3-performance-model
**Author:** codex
**Status:** captured   <!-- captured | drained -->

## Decision

- Le requires future WaferEngine development for the Wavel adoption work to
  occur in a new isolated worktree and new development branch based on a
  freshly verified `lexu/staging/kv-feature`, not in the dirty
  `/home/lexu/WaferEngine-staging` checkout.
- The frozen offload-study evidence and future development base are separate
  boundaries. At `2026-08-30T00:01:55Z`, local and advertised remote refs were
  `m3-on-chip-kv-offload-study@255dab72c4231f85c28a82007bf4c2830696537d`
  and `kv-feature@f5252b3428cb0197e364beb2954457ed98467e2f`; they diverged
  after merge base `77d6d407328f46314c90238d799f9ed5402d55b6`.
- Worktree creation is not implicit planning authority. Reverify the base and
  obtain/select the destination path and development-branch name before the
  separately authorized setup action.

## Implications

- M1-S1b remains a read-only evidence audit and can inspect the frozen commit
  through Git objects without waiting for the development worktree.
- Never substitute the offload-study head for the development base or describe
  the historical merge base as the current `kv-feature` head.

## Pointers

- `/home/lexu/wse3-performance-model/ROADMAP.md`
- `/home/lexu/wse3-performance-model/PROGRESS.md`
- `/home/lexu/wse3-performance-model/milestones/M1-wavel-pipeline-placement-plan.md`
