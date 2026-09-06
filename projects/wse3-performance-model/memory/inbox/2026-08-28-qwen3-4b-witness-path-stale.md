# Qwen3-4B witness path is stale — 2026-08-28

**Project:** wse3-performance-model
**Author:** codex
**Status:** captured   <!-- captured | drained -->

## What happened / finding

- When starting M1-S1 from the current roadmap, the historical witness path
  `/home/lexu/worktrees/1.7b-pipeline-af@93a6d0e/models/qwen3_4b-decode`
  does not exist on gala2 as of 2026-08-28. It must not be treated as a live
  revision boundary or silently replaced.
- Bounded locator checks found
  `/home/lexu/worktrees/1.7b-pipeline-af/models/qwen3_4b-decode` and
  `/home/lexu/WaferEngine-staging/models/qwen3_4b-decode`, but neither has been
  established as the canonical M1/S4 baseline. Their repo roots, revisions,
  configs, provenance, and relationship to the historical `@93a6d0e` identity
  remain to be source-audited.

## Implications / next actions

- [ ] In M1-S1, record the missing historical path as a stale dependency and
  audit the two bounded locator candidates without freezing either one.
- [ ] Leave canonical baseline selection to M1-S4 unless direct provenance
  evidence resolves it earlier.

## Pointers

- `/home/lexu/wse3-performance-model/ROADMAP.md`
- `/home/lexu/wse3-performance-model/milestones/M1-wavel-pipeline-placement-plan.md`
- `/home/lexu/wse3-performance-model/docs/session-prompts/2026-08-28-M1-S1-wavel-source-capability-audit.md`
