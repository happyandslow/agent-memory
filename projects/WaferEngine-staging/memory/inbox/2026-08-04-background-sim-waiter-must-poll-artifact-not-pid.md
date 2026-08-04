---
date: 2026-08-04
project: WaferEngine-staging
tags: [tooling, gotcha, sim, container, background-jobs, methodology]
---

# A background waiter for a containerized sim run must poll for the output artifact, not track a PID — 2026-08-04

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured

## The situation this applies to

You launch a `cs_python launch_sim.py` (or `run_sim.sh`) sim in the background and write a
helper "waiter" that is supposed to block until the run finishes and then snapshot its
artifacts (`device_verdict.json`, `sim_port_map.json`, `rv_*` dirs) — typically to compare a
refactor against a preserved baseline, or to continue a multi-step pipeline unattended. The
run completes on disk, but **the waiter never copies anything**, and a later session finds the
snapshot empty / has to confirm completion by hand.

## What happened / finding

- Root cause (confirmed by Le): the waiter **watched the outer shell PIDs**, but the actual
  work runs inside the SDK **SIF container as a child Python process with a different PID**.
  The outer shell exits (or is the wrong thing to `wait` on) while the container Python is
  still compiling/decoding, so PID-based completion fires early or on the wrong process and the
  post-run copy step is skipped.
- This bit **twice** across the R0b refactor sessions — the same wrong-PID waiter pattern was
  rewritten and still failed — which is what makes it worth recording rather than a one-off.
- The robust fix is to **poll for the completion artifact itself** (e.g. loop until
  `<out>/device_verdict.json` exists and is non-empty), not to track any PID. The verdict file
  is the true "wire-complete" signal; a PID that crosses the process/container boundary is not.
- Aggravating factor: the SIF sim is slow (~30 s/step; a retain config is ~32 steps), so a
  waiter that gives up on a short PID-based timeout looks "done" long before the run is.

**Promotion candidate (procedural):** this is a method for a class of situations — any
background completion-waiter for a containerized job on these boxes — not a WaferEngine fact.
If it recurs again, it belongs in an operational note/skill, not a topic.

## Implications / next actions

- [ ] When scripting unattended sim runs: poll for the output artifact, never `wait $PID` /
      PID-match across the container boundary.
- [ ] Pair with the known disk gotcha: always go through `run_sim.sh` (or set
      `CSL_SUPPRESS_SIMFAB_TRACE=1` / `SINGULARITYENV_CSL_SUPPRESS_SIMFAB_TRACE=1`) so a bare
      `cs_python launch_sim.py` does not write ~100 GB of simfab traces onto the shared disk.

## Pointers

- Context: R0b behavior-preserving refactor of `models/qwen3_1p7b-decode/launch.py`, comparing
  refactored sim output bit-for-bit against a pristine baseline.
- Related: [[2026-07-28-prove-same-source-before-comparing-timings]] (the bit-identity
  comparison the snapshot feeds), [[2026-07-26-sdk-container-cannot-mount-tmp]] (same SIF
  container constraints).
