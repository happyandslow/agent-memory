# CS-3 gotcha — when the gateway ssh dies mid-run, the timeout guard's csctl-cancel never fires — 2026-07-21

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured

## The situation this applies to

You launched a device run on CS-3 through the `cs3-run.sh` timeout guard. The run
exits `rc=255`, and the per-point log's last line is `Timeout, server cerebras
not responding.` (preceded by the benign `InconsistentVersion` and `Could not
find coordinator` lines — those are NOT the cause). You cannot ssh back in;
banner exchange times out. Question you must ask: **is a wafer job still running
that I can no longer see or cancel?**

## The finding

`cs3-run.sh`'s cleanup — `csctl cancel` on overrun — only fires when the guard's
own **timeout** trips (the run overran its budget). It does **not** fire when the
**ssh transport itself dies** first: the ssh process returns `rc=255`, the guard
exits immediately without reaching its cancel path, and if a wafer `execute` job
had already started it is now **orphaned** — still holding a wafer on the shared
cluster, with no local process tracking it and (until the gateway recovers) no
way to `csctl cancel` it. This is a *different* failure mode from a timeout
overrun, and the existing "killing local ssh doesn't stop the appliance job"
note doesn't cover it, because here even the guard's cancel never runs.

Observed this session: `p2_L16384_k48`'s first attempt died exactly this way
(`Timeout, server cerebras not responding`, rc=255) after the job had started;
the remaining batch points then failed instantly. On reconnect the job had
already cleared on its own, but that is luck, not cleanup.

## What to do

- **Symptom → action:** `Timeout, server cerebras not responding` + `rc=255` on a
  device run ⇒ treat a wafer job as *possibly orphaned*. The moment the gateway
  is reachable again, run `csctl get jobs | grep <user>` and cancel any survivor
  before submitting new work — a leaked job just queues everything behind it.
- **Harden the driver:** an outer batch script should, on any non-zero device-run
  rc, probe the gateway and print an explicit "CHECK MANUALLY for orphan jobs"
  when it can't reach `csctl` to self-verify — do not silently move on.
- Distinguish this from a real overrun: an overrun log ends at the guard's
  kill/cancel with a 124; this ends at an ssh `Timeout` with 255 and no cancel.

## Implications / next actions

- [ ] Promotion candidate for the **cs3-runner** skill: add the ssh-death case to
  its cleanup section (currently only the timeout-overrun cancel is documented).
  Procedural, cluster-general, states without naming a specific run.

## Pointers

- `~/.claude/skills/cs3-runner/scripts/cs3-run.sh` (the guard whose cancel is
  bypassed)
- Companion operational notes already in
  `memory/inbox/2026-07-19-prefill-prefix-reuse-real-scale-perf.md` (out_* don't
  persist to the login node; keep remote `~` literal) — same "looks like a
  cluster fault, read the log first" family.
