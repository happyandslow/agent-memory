# Source-comment lossless compression gate — 2026-08-11

**Project:** WaferEngine-staging
**Author:** codex
**Status:** drained

## Situation / finding

When a feature branch accumulates long module docstrings and comments that narrate
milestones, temporary implementation choices, or future work, the history can hide
the stable contract and later become actively misleading. A safe cleanup should keep
only information that the code and types do not make obvious: units, hardware or wire
ordering, atomicity boundaries, trust boundaries, and fail-closed conditions.

Remove milestone labels, implementation chronology, repeated call-flow narration,
and speculative next steps. Do not compress away the reason for a non-obvious
validation or protocol constraint.

For a comment/docstring-only cleanup, validate more strongly than a visual diff:

1. Compare the pre-cleanup and post-cleanup Python ASTs after stripping module,
   class, and function docstrings; they must be identical.
2. Run `git diff --check` and the full relevant regression suite.
3. Check the index before and after; comment cleanup is not permission to stage or
   commit, and unrelated untracked artifacts remain untouched.

This gate was exercised on 23 Python files in the M1 inner-PE-reuse branch: the diff
removed 1,006 net lines, all executable ASTs remained identical to HEAD, and the full
decode host suite passed 414 tests.

## Implications / next actions

- [ ] Apply this gate when future source-comment cleanup spans multiple modules.
- [ ] If this procedure recurs outside WaferEngine, consider promoting it to a
      reusable documentation-cleanup review skill.

## Pointers

- Branch: `lexu/staging/m1-inner-pe-reuse`
- Validation baseline: HEAD `4c3a3bb`
- Main reviewed modules: `round_planner.py`, `round_plan.py`, `round_input.py`,
  `kv_store.py`, and `launch.py`
