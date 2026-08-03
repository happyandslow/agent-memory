# The retry wrapper died and the run kept going — so nothing retried and nothing collected — 2026-07-31

**Project:** WaferEngine-staging
**Author:** claude
**Status:** drained

Refines [[2026-07-30-cs3-relaunch-loop-guards-and-a-cheap-store-build]]. Only the parts that
note does not already cover.

## Symptom

A guarded CS-3 driver is launched with `setsid nohup ./run.sh ... &` over ssh. Later the run
appears **dead** — `pgrep` finds no wrapper, the log ends mid-staging with no rc line and no
completion marker. But the wafer job is fine: `csctl get jobs` shows it RUNNING and
`launch_device.py` is alive, **reparented to init (ppid=1)**.

## What actually happened

The wrapper shell died; its child survived. Consequences, all silent:

- **no retry** — the 502 that killed that attempt was never retried, even though the loop existed
- **no collection** — the wrapper's post-steps (`cp timing.json` into `evidence/`, completion
  marker) never ran, so results existed only under the launcher's own path

⇒ **Put the retry loop in a script that does nothing else, and never rely on the wrapper for
result collection.** Check `csctl get jobs` and the child process before concluding a run died —
absence of the wrapper proves nothing about the run.

## A second pgrep failure mode, distinct from the one already recorded

The 07-30 note covers `pgrep -f` matching **its own command line** (fix: `[l]aunch`). This is the
opposite error and it produced a **false negative**:

```bash
pgrep -f "[l]aunch_device --mode reload"     # never matches
pgrep -f "[l]aunch_device.py --mode reload"  # the real cmdline has .py
```

Used as an `until` loop condition it terminated immediately and I reported "driver exited" to the
user while the run was healthy. **Both pgrep failure modes are silent and both look like a
plausible state.** Print the matched PID and cmdline when a guard makes a decision, rather than
branching on a bare exit code.

## Implications / next actions

- [ ] Procedural and cross-project (see § promotion) — pairs with the self-match trick already
      recorded. Together they are the whole of "guarding a long remote run with pgrep".

## Pointers

- `m2bench/e9_serve.sh` (serve-only retry loop, the shape that worked)
- Cost this session: one lost retry cycle on an EPCC 502, plus a false status report.
