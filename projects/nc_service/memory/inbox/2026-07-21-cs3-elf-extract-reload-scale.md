# Extracting a compiled kernel's ELF off CS-3, and why the reloadable artifact is 23 GB/phase (not lightweight)

Date: 2026-07-21 · Repo: `nc_service` (WaferEngine `launch_device.py` patched in a worktree)

**Project:** nc_service
**Author:** claude
**Status:** captured

## Situation

Goal: compile the pdSeparate kernel on a CS-3 worker (compile-only) and download the
ELF so the `csl-kernel` bundle's `serve()` can run compile-once/load-many locally —
i.e. exercise the real kernel and iterate without recompiling. Symptom that sends
you down this hole: `launch_device.py` compile-only uses `dl=[]`, so it compiles
both phases (~420 s prefill / ~90 s decode at 524288 PE) and then **downloads
nothing** — the ELF is only on the ephemeral worker pod.

## Getting the ELF off the worker — what works and what does not

- **`download_artifact` does NOT work for run-time-created files.** It resolves
  names against the uploaded *staging* snapshot (`<artifact_id>/<name>`), so a file
  you `tar` into the shell CWD at run time gives `FileNotFoundError`. On a big dir
  it gives a gRPC `_MultiThreadedRendezvous` — but the framework swallows the real
  status (`except Exception: print(type(e).__name__)`), so **"too large" was a wrong
  guess**: the tarballs were only 13.5 MB / 862 KB. It is a path-resolution failure,
  not a size limit.
- Worker FS is **not shared** with the login node (worker `$HOME=/`, `/n1/wsjob/...`
  does not exist on login), and the workdir is wiped when the job ends — so you
  cannot rsync the ELF directly.
- **What works: `csctl log-export <jobid> -b -c -p <dir>`.** `-c` = compile
  artifacts (metadata: `sim.symbols/params`, `plan.json`, `fabric.json`,
  `sim_port_map.json`), **`-b` = binaries including `executables/*.elf`**. `-c`
  ALONE does NOT include the ELF (elf_count=0). It works **even after the job has
  ended** (the cluster retains artifacts). Give `unzip` a long timeout — the archive
  has hundreds of tiny ELFs and unzip alone exceeds 120 s.
- Live alternative (job still running): the e16 pattern `launcher.run("base64
  <worker_file>")` reads a worker file out through the launcher context — bypasses
  `download_artifact` entirely. Only usable while the SdkLauncher context is open.

## The reload reality: the loadable artifact is ~23 GB/phase, not the 73 MB subset

- `SdkCompileArtifacts(bindir).add_port_mapping(port_map)` reload API is real and
  present in the **full SDK (`cs_python`)** — NOT in the login-node `csl` conda env,
  which is **client-only** (`cerebras.sdk.client` for SdkLauncher/SdkCompiler
  staging; no `cerebras.sdk.runtime`).
- Construct + add_port_mapping succeed on a 73 MB bindir (executables only, no
  `sim.elf`). But `SdkRuntime` needs kernel ELFs **in the bindir root** (it globs
  `*.elf` there; a `sim/` subdir gives "No kernel ELFs found"), and even flattened,
  the per-region `executables/*.elf` are **1×1-fabric ELFs** → load fails "ELF
  compiled for fabric 1x1 on a system 762x1172". **The loadable whole-device image
  is `sim.elf` ≈ 23 GB/phase** (46 GB both phases, and still mock weights → garbage
  output). This should not go into the bundle's git.

**Consequence for the plan:** you cannot cheaply package a mock-weight compiled
artifact for local reload iteration — reload works mechanically but the payload is
23 GB/phase. Do reload/R0–R5 validation on the cluster in place; keep the bundle at
stub ELF + real port_map. Real answers still require a `--weights-dir` real-weight
compile (weights are baked at compile time via `set_symbol_all`, same 23 GB scale).

## Kept: the real port_map IS reusable

Both phases' real `sim_port_map.json` were extracted and written into the bundle
(`artifacts/{prefill,decode}/port_map.json`, replacing `{"ports":[]}`). Port/LVDS
layout is **structural and weight-independent → valid for the real-weight version
too**. Compile cache (`SDK_RT_ALREADY_COMPILED`) does NOT persist across jobs, so
every attempt is a full ~510 s compile — no cheap iteration.

## Operational: reuse the persistent ControlMaster, don't reopen the gateway

The flaky EIDF gateway drops connections when you run per-command `cs3-ssh.sh CS-3`
(new gateway hop each time). Routing every command through the resident 8 h
ControlMaster (`ssh CS-3-cmd`) is stable — it survived a long profiling/compile
session where fresh connections kept dropping. **Promotion candidate** for the
cs3-runner/cs3-run skill: prefer the persistent `CS-3-cmd` channel over new hops.
