# Driving codex-review in a loop: background passes finish with empty output, foreground passes time out

**Project:** WaferEngine-staging
**Author:** claude
**Status:** drained

## The situation this applies to

You are iterating a plan or diff through the local `codex-review` CLI in a loop
(review → fix → re-review until approve), and launching each pass in the background so
you can keep working. Symptoms: a backgrounded pass "completes" with **exit 0 but writes
no new raw-findings file** (so `ls -t` hands you the *previous* round's output and you
almost misreport a stale review as the new verdict); meanwhile a foreground pass runs
**past the tool's ~10-minute cap and gets killed**. It looks like Codex-side load, a
stale-read bug, or flakiness. Confusingly, right after the user resets Codex a pass
runs fine — which makes it look intermittent.

## The cause and the fix

The wrapper **inherits the caller's stdin**, and the `codex` CLI **blocks waiting on
stdin**. Under `nohup`/background with the pipe held open by the caller, it waits
forever → empty exit-0. In the foreground it just runs until the tool timeout kills it.

Fix: **redirect stdin from `/dev/null`** (`... </dev/null`) when launching in the
background. The pass then completes normally and writes its raw file. (The user's own
interactive `codex` runs worked because their terminal supplies an stdin that closes.)

## Two adjacent disciplines this cost real time to learn

- **A timeout is not a clean review.** A single 900 s / 1800 s pass that produces
  nothing is a *failure*, not an approval and not "converged." Do not report a pass,
  do not infer "no more issues" — retry (cheaply) instead. Earlier rounds of the same
  plan completed in <600 s, so a sudden long silence means the harness, not the plan.
- **Verify the raw file you read is actually the new one** (check its mtime against the
  launch time), because `ls -t` after a no-output run points at the prior round and the
  contents can be byte-identical to it.

## Promotion candidate

Procedural, tooling-level, and independent of this project — belongs in the
`codex-review` skill (background-launch recipe + "timeout ≠ pass"), not a WaferEngine
topic.

## Pointers

- `~/claude-skills/codex-review/scripts/run_codex_review.py` (the wrapper)
- codex-review skill
