# Agent-memory repository conflicts

## 2026-08-20 — local branch diverged from origin/main

- Daily maintenance `git pull --ff-only` could not run because `main` is ahead 7 and behind 1 relative to `origin/main`.
- Local-only commits: `cfd5ef7`, `84ddb2d`, `fe92a54`, `fb5e3a8`, `f0c1742`, `6bafcb9`, `8e02cd6`.
- Remote-only commit: `1709f5a memory: daily reflect captures 2026-08-19 (cron)`.
- Cron did not push or rebase. Le/manual resolution needed: inspect and reconcile divergence, then push or reset intentionally.

## 2026-08-25 — local branch still diverged from origin/main; pull blocked by binary worktree change

- Daily maintenance could not safely start with `git pull --ff-only`: `main` is ahead 1 and behind 6 relative to `origin/main`.
- Local-only commit: `6088518 memory: daily work maintenance 2026-08-24`.
- Remote-only commits at status time: `dd06c1c`, `7487863`, `e9e480b`, `c5a7280`, `bf77964`, `ee67297`.
- Worktree also has a modified binary meeting deck: `projects/WaferEngine-staging/meetings/2026-08-24.pptx` (`1809578 -> 2343557` bytes in `git diff --stat`).
- Cron did not push, rebase, reset, or overwrite the deck. Le/manual resolution needed: decide whether to preserve/commit the PPTX change, then reconcile `main` with `origin/main`.

## 2026-08-26 — local branch still diverged from origin/main; pull blocked

- Daily maintenance attempted `git pull --ff-only`; it failed with `fatal: Not possible to fast-forward, aborting.`
- Status after fetch: `main` is ahead 2 and behind 7 relative to `origin/main`.
- Local-only commits: `e1eff72 memory: daily work maintenance 2026-08-25`; `6088518 memory: daily work maintenance 2026-08-24`.
- Remote-only commits at status time: `2d0d6c6`, `dd06c1c`, `7487863`, `e9e480b`, `c5a7280`, `bf77964`, `ee67297`.
- Worktree still has a modified binary meeting deck: `projects/WaferEngine-staging/meetings/2026-08-24.pptx` (`1809578 -> 2343557` bytes in `git diff --stat`).
- Cron did not push, rebase, reset, or overwrite the deck. Le/manual resolution needed: decide whether to preserve/commit the PPTX change, then reconcile `main` with `origin/main`.

## 2026-08-28 — local branch still diverged from origin/main; pull blocked

- Daily maintenance attempted `git pull --ff-only`; it failed with `fatal: Not possible to fast-forward, aborting.`
- Status after fetch: `main` is ahead 3 and behind 10 relative to `origin/main`.
- Local-only commits: `9194317 memory: daily work maintenance 2026-08-26`; `e1eff72 memory: daily work maintenance 2026-08-25`; `6088518 memory: daily work maintenance 2026-08-24`.
- Remote-only commits at status time: `ffb93b1`, `27c0ba3`, `e51f788`, `2d0d6c6`, `dd06c1c`, `7487863`, `e9e480b`, `c5a7280`, `bf77964`, `ee67297`.
- Worktree still has a modified binary meeting deck: `projects/WaferEngine-staging/meetings/2026-08-24.pptx` (`1809578 -> 2343557` bytes before this maintenance pass).
- Cron did not push, rebase, reset, or overwrite the deck. Le/manual resolution needed: decide whether to preserve/commit the PPTX change, then reconcile `main` with `origin/main`.
