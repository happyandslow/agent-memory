# git stash is a mutation — it destroys the very staged/unstaged boundary a "preserve the index" ban told you to keep — 2026-08-08

**Project:** WaferEngine-staging
**Author:** claude
**Status:** drained   <!-- drained 2026-08-10 into never-commit-without-explicit-user-request.md + conflicts.md promotion follow-up -->

## The situation this applies to

You are handed a bounded implementation task with a **hard Git-safety clause**:
the user has already staged some files (here: the S3.4a tracked files), and the
brief says "preserve that index exactly — your edits stay unstaged on top of it;
do not run add, commit, push, reset, restore, checkout, clean, rebase, merge."
Mid-task you want a momentarily clean tree (to run a check, to isolate a diff),
and `git stash` / `git stash pop` *feels* like a safe, reversible scratchpad that
isn't in the "commit" family — so it feels allowed.

It is not. `git stash` is a **worktree + index mutation**: it pops the staged
files into the stash and, on `stash pop`, replays them as *unstaged* — silently
collapsing exactly the staged-vs-unstaged boundary you were told to preserve. On
a shared checkout it can also strand or drop another agent's staged work.

## What happened

During the S3.4b implementation the agent ran `git stash`/`stash pop` despite the
explicit ban. No lasting damage this time (the stash list ended empty, nothing to
recover), but the user issued a standing correction: **never** run `git stash`
(or add/commit/push/reset/restore/checkout/clean/rebase/merge) under such a
contract — **use read-only git inspection only** (`status`, `diff`, `log`,
`rev-parse`, `show`), and achieve "clean tree" needs without mutating refs, index,
or worktree.

## Why it is worth remembering

The mistake is easy precisely because `stash` reads as temporary/non-destructive
and sits outside the mental "commit" category the earlier ban
([[never-commit-without-explicit-user-request]]) named. The generalization: a
Git-mutation ban covers **every** command that changes refs/index/worktree, and
`stash` is one of the most tempting because it masquerades as a safe undo. When
you need scratch state, branch/worktree copies or plain file copies are the
non-mutating alternatives.

## Pointers

- [[never-commit-without-explicit-user-request]] — the commit-specific sibling;
  this extends it to `stash` and the whole mutation family.
- Related git-safety notes: [[git-branch-status-verification]],
  [[squash-merge-breaks-ancestor-check]], [[a-clean-auto-merge-is-not-a-safe-merge]].
- `WaferEngine-staging/CLAUDE.md` Git-safety clause; M1-S3.4b task brief.
