# M2 on real CS-3: the whole bridge stack now works up to the decode handover — and the thing that blocks it also breaks the KERNEL'S OWN validated reload path

Date: 2026-07-29 (overnight session) · Repo: `nc_service`, branch `lexu/pdsep-kernel-integration`

**Project:** nc_service
**Author:** claude
**Status:** captured

## The headline

Eight device attempts. Everything below the decode handover now works on the real
machine, including a **wafer prefill that reproduces to the cycle across runs**. The
remaining blocker is not in our architecture: a **control experiment running the
kernel's own unmodified `launch_device.py --mode reload` against the same store fails
in the same place, with the same 502.** Whatever this is, it is upstream of us and
affects a path whose `device_verdict.json` says `artifact_mode=cached_reload`, PASS.

Do not spend the next session re-deriving our side. Start from the control.

## What now works on device (do not re-litigate)

Compile from our vendored tree → a complete, reload-servable store at
`~/lexu/sd_m2_store/serve_2x4_8k20k` (prefill 3.2 GB, decode 3.1 GB, tokenizer 11 MB,
`build_manifest.json`, `serve_meta.json` in both phases). All 36 fingerprinted sources
match our tree exactly.

Then, in one bring-up: 6.6 GB byte-split upload → reassembly → `zstd -d` → controller →
RPC hotswap → our `build_handlers` on the pod → artifact read → tokenizer →
**prefill on the WSE-3** → KV bridge. `bringup_s = 519 s`.

Real device numbers, from the pod log, identical across two runs:

    runtime.load           146.6 s
    PREFILL_LEN            19 tokens
    span cycles            48419604      (48420135 the other run)
    forward @ 0.85 GHz     56964 us      -> 333.5 tok/s
    recv first token       64.8 ms
    KV egress recv         23.3 ms
    first_token            9707

## The blocker, stated precisely

Every attempt dies at the prefill→decode handover. From the exported pod logs (use
`csctl log-export <jobid> -p <dir>`; it works after the job ends):

    run 7: prefill verdict 01:52:46 -> container SIGTERM 01:53:50
    run 8: prefill verdict 02:10:19 -> container SIGTERM 02:11:23

**64 s to the second, twice.** No decode output in ANY run — `launch_decode.serve()`
never reaches its own `runtime.load`. The container's own message says
*"expected cleanup behavior after client side has terminated job"*, i.e. it was reaped,
not crashed.

Two candidate mechanisms, still undecided:
- the appliance reaps a job ~60 s after the last `SdkRuntime` detaches (the prefill
  child's `finally: runtime.stop()`), and our decode side cannot re-attach in time
  (~60 s copy + ~147 s load);
- or `get_platform(cmaddr)` on the decode side attaches as a SECOND client while the
  launcher session is live, and that is what terminates it.

A third observation constrains the search: `__IOP_INIT__` succeeded when it took 519 s
but the control's single long `launcher.run()` was 502'd after ~14 minutes of silence,
so there is also a **silent-RPC ceiling somewhere between 9 and 14 minutes**. That alone
rules out "just block until the decode is loaded" — which was tried, and is why blocking
init did not help.

## The control experiment is the finding

`launch_device.py --mode reload --request request_config/sd_smoke/request.json --store
<our store>` — the kernel's own code, unmodified, our store — **fails the same way**,
502 inside `d.run(run_cmd)`, with no worker output at all.

That is the single most useful fact from the night: it converts "our integration is
broken" into "this path is broken on this cluster right now, for upstream too". Next
session should establish whether the kernel's reload works at all today (try its
`mtbench8` request, and the pre-existing `~/lexu/m2bench` e2e store) before touching
our code.

It also independently confirmed our staging design — its own uploader reports
`2 byte-split + 2106 base-upload file(s) (no tar)`, exactly the split we converged on.

## Four device-run defects we found and fixed (all in the working tree, uncommitted)

1. **`MAX_ARG_STRLEN` at bring-up.** A real store is 2108 files; routing all of them
   through byte-split staging built a reassembly shell command over the 128 KB
   per-argument limit → `[Errno 7] Argument list too long: '/bin/sh'`, after the whole
   upload. Fix: small files ride the base tree upload, only over-budget files split —
   the same split the kernel's own uploader makes. Worth remembering *why* the limit
   applies: **before** the patch is installed, `launcher.run()` is a real `/bin/sh -c`
   exec; **after** it, the frame is a gRPC string field with no shell limit. Same method
   name, two execution models either side of the hotswap.
2. **Pod path resolution.** Relative `IOP_SD_*` paths were joined to `Path.cwd()`. The
   measured layout is `<worker-0>/` for the patched worker process but
   `<worker-0>/<staging_name>/` for `launcher.run()` AND for both upload channels. Fix:
   resolve against `IOP_SRC`.
3. **`/dev/shm` is 64 MB on this pod** (working volume: 222 GB free). The kernel's own
   comment suggests tmpfs for the KV handoff; a run took that advice, completed the
   wafer prefill, and died in `np.savez` with ENOSPC.
4. **Unbounded init retry (mine).** Retrying `__IOP_INIT__` through ingress 502s is
   right, but I bounded it by `ready_timeout_s` (4200 s) — a budget that exists to cover
   a slow call that has NOT failed. Against a dead job it hammered a dead endpoint every
   5 s for an hour. Now a separate 60 s retry budget.

## Two procedural lessons worth keeping

**When remote-layout evidence conflicts, probe — do not infer.** Two runs' tracebacks
let me build a confident and wrong model of the pod filesystem, and the "fix" it produced
(a `cp -a` merge) actively broke the next run. A 20-line probe that opened a launcher,
staged one marker file and printed `pwd` settled it in one short job. Same again for the
disk: one `df -h` beat another round of guessing.

**When a subagent reports "I diverged from your design, the cost is N", verify N.** W3
flagged that small files were going through the parts channel and estimated "~30
`stage()` calls rather than 4". I accepted it. The real number was 2108, and the
consequence was not slowness but a hard failure. The estimate was the thing to check.

## State of the tree

**Nothing committed** (S1/S2 were checkpointed by Le as `9f0d2d5`, `08ecf82`; everything
after is working-tree). Suite **653 passed / 2 skipped**. New: `sd_device_check.py`
(the device driver), `chunked_stage.py`, `device_timing.py` (recovers the decode TSC by
rebinding `launch_decode._serve_loop` — the kernel collects an 8-word burst per batch and
then discards it, so there is otherwise NO device number on this path), `stage_join.py`,
plus `plan_cache_upload`, the bridge's `stage_parts`/`prep_cmds`, and the widened
in-process timing ring.

Full narrative, in order, with every measurement: `M2_NIGHT_LOG_2026-07-28.md` at the
repo root.

## Pointers

- Store: `CS-3:~/lexu/sd_m2_store/serve_2x4_8k20k`; run tree `~/lexu/sd_m2/`;
  exported pod logs under `~/lexu/sd_m2/logs/<jobid>/`.
- `scratchpad/sd_guarded_run.sh` — replacement for `cs3-run.sh`: routes through the
  resident `CS-3-cmd` ControlMaster, and on timeout cancels ONLY job ids that appeared
  after launch. **`cs3-run.sh` calls `cancel-mine` on overrun, which sweeps every job
  under the shared login — that is a defect in the shared skill.**
- Related: [[2026-07-28-m2-s1s2-staging-and-real-cfg]],
  [[2026-07-28-m1-complete-bridge-architecture-index]], [[cs3-restore-grpc-502-gotcha]].
