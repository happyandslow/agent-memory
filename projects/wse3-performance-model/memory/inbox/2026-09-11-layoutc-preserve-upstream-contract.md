# LayoutC acceptance should preserve upstream behavior — 2026-09-11

**Project:** wse3-performance-model
**Author:** codex
**Status:** captured

## What happened / finding

- When deciding whether tall A2 is acceptable after numerical attribution, Le clarified that the project should preserve the original implementation's computational behavior while changing placement and communication. Changing operators or evaluating their performance impact is outside this task.
- The upstream/NumPy operator mismatch is inherited context, not a request to improve SiLU or other operators. This supersedes the prior report's suggestion to consider operator changes as the next step.
- No new numerical tolerance was approved by this clarification. Measured tall/upstream random L2 is 0.147389%, but maxabs is 4; passing an L2-only bound is distinct from passing the previous combined L2/maxabs rule.

## Implications / next actions

- Use pinned original 4B behavior as the primary regression baseline. Continue layout/data-path and complete-group correctness work; preserve the numerical attribution evidence and distinguish it from untested inputs or configurations.

## Pointers

- [Measured attribution and scope](/home/lexu/wse3-performance-model/docs/reports/2026-09-11-layoutC-upstream-numerical-attribution.md:74).
