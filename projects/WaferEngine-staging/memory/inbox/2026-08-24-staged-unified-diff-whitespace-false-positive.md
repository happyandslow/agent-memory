# Staged unified diff whitespace false positive — 2026-08-24

**Project:** WaferEngine-staging
**Author:** codex
**Status:** captured

## What happened / finding

- When `git diff --cached --check` reports many trailing-whitespace warnings
  in a staged file that is itself a unified diff, inspect the two diff layers
  before treating every warning as source damage. A blank context line in the
  inner unified diff is one space; the outer Git diff prefixes the newly added
  file line with `+`, displays `+ `, and flags the inner context marker as
  trailing whitespace.
- In this session, `docs/analysis/m1-s4-c1-decode.diff` accounted for 23 such
  nested-diff warnings. They were false positives with respect to the actual
  CSL source modifications. Pager text such as `:...skipping...` also made the
  output appear more duplicated than it was.
- The same check exposed distinct cases that should not be conflated with the
  nested-diff artifact: three Markdown lines intentionally used two trailing
  spaces for hard line breaks; one code-fence line in
  `docs/analysis/m1-s4-ragged-execution-ab-study.md:123` had an accidental
  trailing space; and `tools/m1_ragged_study/__init__.py` introduced a blank
  line at EOF.
- A trailing space at `decode.csl:318` was verified with `git show HEAD:` to
  predate the change, explaining why the staged check did not report it.
- Prefer not to commit a generated `.diff` when the commit itself is the
  durable source of truth. If a review artifact must be retained, audit the
  repository content separately while excluding that nested-diff file rather
  than suppressing all whitespace diagnostics.

## Implications / next actions

- [ ] Classify `git diff --check` findings by file type and provenance before
      editing; fix real source whitespace while preserving intentional
      Markdown hard breaks and recognizing nested unified-diff markers.
- [ ] Promotion signal: this is a recurring procedural Git-review trap. If it
      appears again, promote it to a compact staged-diff review skill or
      checklist.

## Pointers

- `docs/analysis/m1-s4-c1-decode.diff`
- `docs/analysis/m1-s4-ragged-execution-ab-study.md:123`
- `tools/m1_ragged_study/__init__.py`
- Git branch `lexu/staging/m1-ragged-execution-study`
- Git tip `a24beb4c6c3dcb4595dfd940fe5b8672ae9e1048`
