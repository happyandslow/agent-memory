# Never commit without an explicit user request — 2026-07-29

**Project:** WaferEngine-staging
**Author:** human
**Status:** drained

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
