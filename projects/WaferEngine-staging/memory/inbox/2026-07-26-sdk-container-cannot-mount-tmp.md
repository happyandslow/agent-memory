# `container creation failed: … doesn't exist in container` — the Cerebras SDK singularity image cannot bind-mount anything under `/tmp`

Date: 2026-07-26 · Repo: `WaferEngine-staging` · SDK 2.10.0, gala2

**Project:** WaferEngine-staging
**Author:** claude
**Status:** drained

## The situation this applies to

You want to run a kernel from somewhere other than the repo working tree — most commonly a
**second checkout for an A/B comparison** (`git worktree add <path> HEAD`, then run the same
config on pre-change code to prove a change is inert). You put the worktree in a scratch
directory under `/tmp`, run `run_sim.sh` there, and it dies immediately — before any compile,
with no CSL error:

```
FATAL:   container creation failed: mount /tmp/.../models/qwen3_1p7b-decode
  -> /tmp/.../models/qwen3_1p7b-decode error: while mounting /tmp/.../models/qwen3_1p7b-decode:
  destination /tmp/.../models/qwen3_1p7b-decode doesn't exist in container
```

## The cause and the fix

`cs_python` runs inside a singularity image (`sdk-cbcore-*.sif`) and bind-mounts the working
directory into the container at the **same absolute path**. The container supplies its own
`/tmp`, so a host path under `/tmp` has no valid mount point inside — the bind fails and the
run never starts.

**Fix: put the worktree under `$HOME`.** `/home/lexu/wafer-<something>-baseline` worked
immediately with no other change. Remove it afterwards with `git worktree remove --force <path>`
followed by `git worktree prune`.

Note this also rules out the agent scratchpad directory (which lives under `/tmp/claude-*/…`)
as a run location. Scratchpad is fine for logs, dumps and comparison scripts — the process
reading them runs on the host — but **not** for anything `cs_python` must chdir into.

## Confidence

Observed directly this session: the same worktree failed under `/tmp` and succeeded verbatim
under `$HOME`, with nothing else changed. Sim only; a device run was not attempted from an
alternate path.

## Pointers

- Used while establishing the M1-S1 inert gate (baseline = worktree of pre-change HEAD) —
  [[new-storage-axis-only-destinations-take-it]].
- `models/qwen3_1p7b-decode/run_sim.sh` → `cs_python launch_sim.py`.
