---
summary: Never commit without an explicit user request — 2026-07-29
tags: [WaferEngine-staging, drained-inbox, 2026-07-29]
---

# Never commit without an explicit user request — 2026-07-29

This topic was created by the 2026-08-03 maintain pass from a dated inbox capture. Keep it as the durable, topic-scoped home for the finding; the original capture is marked drained.

## Drained capture — 2026-07-29

Source: `memory/inbox/2026-07-29-never-commit-without-explicit-user-request.md`

# Never commit without an explicit user request — 2026-07-29

**Project:** WaferEngine-staging
**Author:** human
**Status:** captured

## What happened / finding

- While other agents were actively working in `/home/lexu/WaferEngine-staging`,
  Codex created commit `91feb24` for a design document even though Le had not
  explicitly requested a commit.
- Le explicitly corrected this behavior: Codex must never create a Git commit
  unless Le directly asks it to commit.
- Approval to design, implement, install, document, or continue is not approval
  to commit. A skill or workflow that normally requires a commit does not
  override this rule.
- This applies especially to shared branches and working trees where other
  agents may be active. Codex must inspect and preserve their staged,
  unstaged, and untracked work.

## Implications / next actions

- [ ] Before every commit, require an explicit instruction in the current user
  request that says to commit.
- [ ] If a workflow or skill asks for a commit without explicit user approval,
  leave the files uncommitted and report that the commit step was skipped.
- [ ] Never infer commit permission from approval of a plan, design, fix,
  migration, or installation.

## Pointers

- `/home/lexu/WaferEngine-staging/CLAUDE.md` already states: “Do not commit your
  code unless the user tells you to.”
- Accidental commit: `91feb24` (to be removed from local branch history while
  preserving its design file as an uncommitted file).

## Update — 2026-08-08: `git stash` is also a mutation

Drained from `memory/inbox/2026-08-08-git-stash-violates-a-preserve-index-ban.md`.

If a task includes a hard Git-safety clause such as “preserve the staged index exactly; your edits stay
unstaged; do not run add/commit/push/reset/restore/checkout/clean/rebase/merge,” then `git stash` is
also banned. It mutates the worktree and index: `stash` removes staged files into the stash, and
`stash pop` can replay them as unstaged, collapsing the staged-vs-unstaged boundary the user explicitly
told the agent to preserve.

Under a Git-mutation ban, use only read-only git inspection (`status`, `diff`, `log`, `rev-parse`,
`show`). If scratch isolation is needed, use a separate copy/worktree or plain file copies rather than
mutating refs, the index, or the shared worktree. This generalizes the commit-specific rule above:
approval to implement or test is not approval to mutate Git state.
