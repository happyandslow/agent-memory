# `cs3-run` remote commands hang when they depend on caller stdin — 2026-09-01

**Project:** WaferEngine-staging
**Author:** codex
**Status:** captured

## What happened / finding

- A remote operation invoked as `cs3-run ssh CS-3-cmd bash -s` with a heredoc
  timed out with RC 124 and produced zero output, even though a preceding warm
  probe succeeded.
- Source inspection of `/home/lexu/.local/bin/cs3-run` showed that it is a
  `pexpect` wrapper that reads child output and responds to the OTP prompt, but
  does not forward the caller's stdin to the child process.
- Therefore commands that require piped stdin, a heredoc, or remote `bash -s`
  wait indefinitely. This symptom is a local transport-contract failure; it is
  not evidence of an authentication, CS-3, or remote-shell failure.
- Remote operations through this wrapper must use an argv-only command. For a
  multi-line operation, transfer a script first (for example with rsync), then
  execute its remote path with an argv-only command.

This is procedural and likely to recur across CS-3 orchestration sessions; it
is a candidate for promotion into the CS-3 run skill after curation.

## Implications / next actions

- [ ] Audit future `cs3-run` command plans for stdin dependence before launch.
- [ ] Preserve a zero-output timeout from a stdin-dependent command as
  transport evidence; do not retry it as an authentication or device failure.

## Pointers

- `WaferEngine-staging/docs/analysis/2026-09-01-m1b-s0-part1-validation-handoff.md`
- `WaferEngine-staging/.s0-artifacts/m1b-s0-a0-real-cs3-runtime-products-20260901T190925Z-f/`
- Related: `2026-09-01-m1b-s0-local-dsr-fmac-witness-contract.md`
