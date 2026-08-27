# Project-session Git safety and prompt policy — 2026-08-27

**Project:** wse3-performance-model
**Author:** codex
**Status:** captured   <!-- captured | drained -->

## What happened / finding

- When any agent works in `wse3-performance-model`, editing, implementing,
  testing, checkpointing, finishing, or being asked to continue is not
  permission to commit or push. `git commit` and `git push` require Le's
  explicit instruction for the exact operation; hooks and automations may not
  bypass this rule.
- Every project work session should start from the repository's
  `docs/session-prompts/_TEMPLATE.md`. The prompt owns one bounded subtask and
  explicitly routes updates among `GOALS.md`, `ROADMAP.md`, `PROGRESS.md`, the
  active milestone, durable artifacts, and qualified agent-memory capture.
- The WaferEngine-staging reference has a reminder-only repo Stop hook plus a
  local agent-memory auto-commit Stop hook, but no Codex-specific hook. Neither
  hook was copied because automatic commits conflict with this project's Git
  policy and the reference checkpoint/reminder wording is internally
  inconsistent.

## Implications / next actions

- [ ] During the next maintain pass, fold this policy into stable project
  memory without duplicating the full prompt template.

## Pointers

- `/home/lexu/wse3-performance-model/AGENTS.md`
- `/home/lexu/wse3-performance-model/docs/session-prompts/_TEMPLATE.md`
- `/home/lexu/wse3-performance-model/WORKFLOW.md`
- `/home/lexu/wse3-performance-model/docs/analysis/2026-08-27-waferengine-staging-agent-hook-audit.md`
