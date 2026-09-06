# CS-3 ops gotchas: `cs3-run ssh … 'bash -s' <<heredoc` hangs forever; env into cs_python needs SINGULARITYENV_ — 2026-09-03

**Project:** wse3-performance-model
**Author:** claude
**Status:** captured

## Situation

A remote command sent through `cs3-run` produces no output for tens of
minutes, the ControlMaster reports healthy, and nothing you launched shows up
in `csctl get jobs` or in the remote log dir. Or an env var you export before
`run_sim.sh` / `cs_python` silently has no effect inside the run.

## What happened / finding

- **`cs3-run ssh CS-3-cmd 'bash -s' <<'EOS' … EOS` hangs.** `cs3-run` is a
  pexpect wrapper (needed to feed the OTP); it does NOT forward the parent's
  stdin, so the remote `bash -s` waits for a script that never arrives. Two
  such calls sat 50 min and the "launched" bench had never started (no script
  file, no log, no job). Symptom: 0 bytes of output, master "running",
  `ps` shows `python3 …/cs3-run ssh CS-3-cmd bash -s` with a long etime.
  **Fix:** once the login is warm, use plain multiplexed
  `ssh CS-3-cmd '<inline command>'` (it reuses the same master) and put any
  script in a synced file (`code/cs3_run_pp.sh`) started under
  `tmux new-session -d`. `cs3-tmux` itself needs a tty ("open terminal
  failed: not a terminal") from a non-interactive harness.
- **Env vars do not reach `cs_python` unless prefixed `SINGULARITYENV_`.**
  `PP_DEPTH=1 ./run_sim.sh …` ran with the default; `SINGULARITYENV_PP_DEPTH=1`
  works (run_sim.sh already does this for `CSL_SUPPRESS_SIMFAB_TRACE`). A
  "DEPTH=1 works" conclusion drawn before noticing this was wrong.
- Concurrent `launch_device_pp.py` runs must not share a staging dir —
  `stage()` rmtree's it while the other session may still be uploading;
  make it per `--tag`.
- After a Claude session restart the CS-3 runs already done were relaunched
  (context lost; `cs3_run_pp.sh <tag>` silently overwrote the remote
  `logs/<tag>.log` and `out_pp_*_<tag>/` of a finished run). Before launching
  anything after a restart, read the analysis doc's job-id list and
  `demo/*/cs3/` first; the script now refuses a tag whose log exists.
- Per-run job accounting: snapshot `csctl get jobs` before/after and cancel
  only the ids that appeared (`cs3_run_pp.sh`); `cancel-mine` sweeps every job
  under the shared login, including other people's sessions.

## Implications / next actions

- [ ] Promotion candidate (procedural, recurring): amend the `cs3-run` skill —
      "heredoc/`bash -s` unsupported; use inline `ssh CS-3-cmd` after the warm
      login" — and the CS-3 runbooks with the `SINGULARITYENV_` rule.

## Pointers

- `wse3-performance-model/demo/4b-pp-demo/code/cs3_run_pp.sh`,
  `launch_device_pp.py`; skill `~/.claude/skills/cs3-run`.
