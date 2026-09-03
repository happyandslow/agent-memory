# Red-fault sims fail by permanent stall, and `timeout` cannot kill the singularity children — 2026-09-03

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured

## The situation this applies to

You run intentional-fault ("red") simulator scenarios wrapped in
`timeout 900 …` and wait for an rc file to adjudicate them. The rc file
never lands; the sim process is still alive 45–60 minutes later, well past
the timeout, sitting at "awaiting logit steps". It looks like the harness
lost the run.

## What happened / finding

- A device assert in a red build does **not** exit the simulator — it
  deadlocks permanently ("awaiting logit steps", 0 DONE markers). The
  fail-closed outcome manifests as a **stall, not a nonzero exit code**, so
  any waiter keyed on rc/exit will wait forever.
- Adjudication rule that worked: after generous wall time (red positives run
  ~5.5 min; these sat 20–60 min), **stall + zero DONE markers = red
  captured (fail-closed) = PASS**. Then kill and record the stall itself as
  the evidence.
- `timeout N` on the wrapper does **not** bound the run: SIGTERM is not
  propagated to the singularity container's child processes, so the wrapper
  dies (or lingers) while the sim survives. Kill the **process tree**
  manually and verify no orphan `cs_python`/singularity remains — and count
  matches carefully, since a grep for the driver name matches your own
  shell line, and unrelated healthy singularity runtimes (e.g. a parallel
  NumPy reference) are also present.
- Same sessions reconfirmed: harness-managed background tasks get killed
  mid-run repeatedly; `setsid nohup` + polling the output artifact (per
  [[2026-08-04-background-sim-waiter-must-poll-artifact-not-pid]]) is the
  reliable pattern for anything long-running.

## Implications / next actions

- [ ] For future red/fault sim gates: budget a stall-detection window
      instead of an exit-code wait, pre-declare "stall + 0 DONE = caught",
      and launch under `setsid` so cleanup can kill the whole tree.

## Pointers

- Session: M1b-S0 Part 2+3 test session, 2026-09-02/03 (red-swap and
  red-live-sentinel scenarios, `models/qwen3_1p7b-decode-ragged-batch/`)
- Related: [[2026-08-04-background-sim-waiter-must-poll-artifact-not-pid]],
  [[2026-07-31-the-retry-wrapper-can-die-while-the-run-survives]]
