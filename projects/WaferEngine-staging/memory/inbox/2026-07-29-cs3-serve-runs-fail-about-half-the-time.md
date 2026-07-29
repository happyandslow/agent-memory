# Half your CS-3 serve runs will die on cluster infrastructure — 2026-07-29

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured   <!-- captured | drained -->
**Promotion:** operational, recurring — reinforces the existing `cs3-runner`
skill promotion candidate already logged in `tracking/conflicts.md`.

## The situation this applies to

You planned "n = 5 runs" for a measurement, budgeted wafer time for five, and
three of them exit non-zero with a Python traceback that has nothing to do with
your code. Or: a run dies and you are wondering whether it left a wafer job
holding the machine.

## What happened / finding

Five identical `--mode reload` serve runs of the same request set, back to back,
on the same store. **Two completed; three died on cluster infrastructure:**

- **runs 2 and 3** — `grpc._channel._InactiveRpcError … Received http2 header
  with status: 502` from the EPCC ingress at `10.27.24.65:443`, mid-run,
  preceded by `Error parsing metadata: … content-type: text/html`. The channel
  breaks and the run cannot continue.
- **run 4** — `ClusterJobInitError: … job failing with pod failure detected …
  first failed pods: [wsjob-…-worker-0]`, during job init.

None were our code: the two that completed were **bit-identical to each other
and to the reference**. No orphan wafer jobs were left — `csctl get jobs` was
clean afterwards, so these failures self-cleaned.

⇒ **Budget attempts, not successes.** A plan that says n = 5 needs ~10 launches
of headroom, or an accept-what-completes rule agreed in advance.

Two operational points that made the difference:

- **Do not drive these with `cs3-run.sh`.** Its timeout path calls
  `cs3-jobs.sh cancel-mine`, and the CS-3 account is **shared** — a blanket
  cancel kills other tenants' jobs. Launch with remote `nohup setsid` into a log
  file and poll the log instead. That also survives ssh transport death (the
  known rc=255 case, where the guard's cancel never runs and a wafer job *can*
  be orphaned). If a run must be killed, cancel the specific wsjob id from the
  log.
- The local ssh call **returning 124 immediately after launching** the detached
  job is normal and does not mean the remote job died — `setsid` outlives it.

## Implications / next actions

- [ ] When a measurement plan states an `n`, state whether it means completed
      runs or launches, and say which was achieved in the report.
- [ ] Reinforces the standing `cs3-runner` promotion candidate: the skill's
      timeout path is unsafe on a shared account, and the nohup+setsid+poll
      pattern is the safer default. Propose, do not install.
- [ ] Worth knowing but **not** established: whether the 502 rate correlates
      with time of day or concurrent tenants. `[unverified]` — n is far too
      small to claim a cause.

## Pointers

- Logs (all five, including the three failures in full):
  `CS-3:/home/eidf217/eidf217/congjiehe/lexu/m2bench/logs/serve_run{1..5}.log`
- Prior, *different* CS-3 failure mode:
  `inbox/2026-07-21-cs3-ssh-death-orphans-wafer-job.md` (transport death, rc=255,
  cancel skipped) — that one *can* orphan a job; these three did not.
- Existing promotion candidate: `tracking/conflicts.md`, 2026-07-22 entry.
