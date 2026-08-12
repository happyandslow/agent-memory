---
summary: Large comment/docstring cleanups should preserve only non-obvious contracts and prove executable equivalence by comparing docstring-stripped ASTs plus normal gates.
tags: [WaferEngine-staging, comments, docstrings, cleanup, ast, regression-gate, review, drained-inbox, 2026-08-11]
---

# Source-comment lossless compression gate — 2026-08-11

When a feature branch accumulates long module docstrings and comments narrating milestones, temporary choices, or future work, source history can hide the stable contract and later become misleading. A safe cleanup keeps information the code and types do not make obvious: units, hardware/wire ordering, atomicity boundaries, trust boundaries, and fail-closed constraints.

Remove milestone labels, implementation chronology, repeated call-flow narration, and speculative next steps. Do not remove the rationale for a non-obvious validation or protocol constraint.

For comment/docstring-only cleanup, validate losslessness more strongly than a visual diff:

1. Compare pre-cleanup and post-cleanup Python ASTs after stripping module, class, and function docstrings; they must be identical.
2. Run `git diff --check` and the full relevant regression suite.
3. Check the index before and after; comment cleanup is not permission to stage or commit, and unrelated untracked artifacts remain untouched.

This gate was exercised on 23 Python files in the M1 inner-PE-reuse branch. The diff removed 1,006 net lines, executable ASTs remained identical to HEAD, and the full decode host suite passed 414 tests.

## Pointers

- Branch: `lexu/staging/m1-inner-pe-reuse`
- Validation baseline: HEAD `4c3a3bb`
- Main modules: `round_planner.py`, `round_plan.py`, `round_input.py`, `kv_store.py`, and `launch.py`
- Source capture: `memory/inbox/2026-08-11-source-comment-lossless-compression.md`