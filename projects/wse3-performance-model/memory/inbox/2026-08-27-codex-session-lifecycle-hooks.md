# Codex session lifecycle hooks — 2026-08-27

**Project:** wse3-performance-model
**Author:** codex
**Status:** captured   <!-- captured | drained -->

## What happened / finding

- When Codex sessions in this project need the standard start protocol and a
  reliable close-time memory review, use the project-local lifecycle config at
  `.codex/hooks.json`. `SessionStart` injects
  `docs/session-prompts/_TEMPLATE.md`; `Stop` continues the first stop attempt
  once so the active model can apply the agent-memory reflect qualification
  bar, then allows the second stop to avoid a loop.
- This supersedes the earlier capture's statement that no reference hook was
  adopted. The project now adopts the checkpoint intent, but not the
  WaferEngine-staging local hook's automatic `git add`/`git commit` behavior.
- A mechanical SessionEnd capture was rejected: SessionEnd output cannot steer
  Codex, while mechanically storing a transcript or session narrative violates
  the agent-memory write contract. The model-reviewed Stop continuation can
  legitimately decide that zero durable captures qualify.
- Both hooks preserve the existing authorization boundary. They do not stage,
  commit, push, run the memory maintain pass, edit generated memory views, or
  expand the session's allowed files and external actions.

## Implications / next actions

- [ ] Review and trust the project hook definition with Codex `/hooks` after
  opening the repository; changed hook hashes are skipped until trusted.
- [ ] During the next maintain pass, reconcile this correction with
  `2026-08-27-project-session-git-safety-and-prompt-policy.md`.

## Pointers

- `/home/lexu/wse3-performance-model/.codex/hooks.json`
- `/home/lexu/wse3-performance-model/.codex/README.md`
- `/home/lexu/wse3-performance-model/docs/session-prompts/_TEMPLATE.md`
- `/home/lexu/wse3-performance-model/docs/analysis/2026-08-27-waferengine-staging-agent-hook-audit.md`
