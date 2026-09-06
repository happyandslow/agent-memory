# Cross-filesystem Git worktree relocation — 2026-08-24

**Project:** WaferEngine-staging
**Author:** codex
**Status:** captured

## What happened / finding

- When a linked Git worktree with tracked and untracked changes must move from
  `/tmp` into a repository-local `.worktrees/` directory, `git worktree move`
  can fail with `Invalid cross-device link` because the two paths reside on
  different filesystems. This failure does not imply that the worktree or its
  changes are corrupt.
- A validated non-destructive relocation procedure is: verify the source
  branch, HEAD, status, and absent target; copy the complete worktree with
  metadata preserved; run `git worktree repair <new-path>` from the main
  repository; verify the repaired branch, HEAD, status, and `git worktree
  list`; compare source and target; only then remove the exact old path.
- `diff -qr` was not a reliable equivalence check here because identical
  broken symlinks produced misleading read errors. `rsync -anic --delete`
  produced no differences, and SHA-256 comparison independently matched all
  22 experiment-source files before deletion of the old worktree.
- Adding `/.worktrees/` to the main repository's local `.git/info/exclude`
  prevents the parent checkout from reporting the nested worktree as
  untracked without creating a tracked ignore-file change.
- For the M1 ragged study, the repaired worktree is
  `/home/lexu/WaferEngine-staging/.worktrees/m1-ragged-execution-study` on
  branch `lexu/staging/m1-ragged-execution-study`. Its local and remote tips
  were both `a24beb4c6c3dcb4595dfd940fe5b8672ae9e1048` when rechecked on
  2026-08-24. The unrelated untracked `docs/slides/` directory remains in the
  worktree and was not modified.

## Implications / next actions

- [ ] Reuse the copy, repair, verify, then delete sequence when moving a linked
      worktree across filesystems; never delete the source before both Git
      registration and content equivalence have been checked.
- [ ] Promotion signal: this is a procedural method that can recur across
      repositories. If it recurs, promote it to a Git-worktree relocation
      skill rather than expanding a project topic.

## Pointers

- `/home/lexu/WaferEngine-staging/.worktrees/m1-ragged-execution-study`
- Git branch `lexu/staging/m1-ragged-execution-study`
- Git tip `a24beb4c6c3dcb4595dfd940fe5b8672ae9e1048`

