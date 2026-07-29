# M2 DELIVERED on real CS-3: the three-way latency split says leg-2 dominates the wafer 3.7x — and the cost inside leg-2 is host work, not transport

Date: 2026-07-29 (overnight session) · Repo: `nc_service`, branch `lexu/pdsep-kernel-integration`

**Project:** nc_service
**Author:** claude
**Status:** captured

## The headline: M2's question is answered

Mock GPU -> gRPC -> gateway -> leg-2 -> REAL serve_loop -> WSE-3, end to end, on the
real machine: **61 rounds, `verifier failures == []`, 61 device TSC rows**, draft ids
differing every round. `bringup_s = 937`, `session_s = 960`.

### The three-way split, draft_len = 4, 61 rounds (p50)

| leg | p50 | share |
|---|---|---|
| **leg-1 verifier round (end to end)** | **20.78 ms** | 100% |
| leg-1 wire (gRPC minus driver work) | 1.25 ms | 6% |
| **leg-2 `launcher.run`** | **19.02 ms** | 92% |
| -- gateway<->worker RPC | 2.59 ms | 12% |
| -- worker handler | 16.44 ms | 79% |
| ---- **device forward span (WSE-3 TSC)** | **5.12 ms** | **25%** |

device p50 5.117 / p90 5.207 / p99 23.87 (one outlier); worker handler p50 16.44 /
p99 17.34; gateway<->worker RPC p50 2.59 / p99 9.39.

**Does leg-2 dominate the device? Yes, ~3.7x.** And the sharper finding: inside leg-2
the transport is NOT the cost (2.59 ms). The cost is the **worker-side host work wrapped
around the device -- 16.44 - 5.12 = ~11.3 ms/round, 54% of the whole round trip**. The
optimisation target is neither the wafer nor the network; it is the host path inside the
worker process.

Scale check against the number the plan told us not to reuse: 5.12 ms for a 4-token
draft batch is ~1.28 ms/token, versus 655 us/token for long-form autoregressive decode
in the kernel's own loop. Different workload -- a draft batch pays per-batch overheads a
steady-state loop amortises.

**Caveat on every number here: the verifier is on LOOPBACK.** leg-1's 1.25 ms is a lower
bound, not a real GPU host across the network (prior work puts that leg at ~41% of a
real round).

Everything below the prefill->decode handover also works, including a **wafer prefill
that reproduces to the cycle across runs**.

**The important correction.** A control experiment — the kernel's own unmodified
`launch_device.py --mode reload` against our store — failed with the same 502, and I
wrote that up as the night's finding: "the blocker is upstream, not ours." **The repeat
control PASSED**, with a full evidence bundle. So:

- our compiled store is good end to end; the kernel served a real request from it;
- the 502s were a **transient ingress degradation**, not a mechanism;
- and every failure of the night sits inside one window (our runs 02:30–03:40, control 1
  at 03:45), with the first attempt after it passing at 04:30.

And the 64-second theory below was indeed an artifact of that window: the same code,
rerun after the ingress recovered, passed. Recorded as a false lead, not a mechanism.

*I had already been told this.* `cs3-loginnode-bst-timezone` records a mode-B 503 that
was "pure-ingress transient, worker healthy". **Rule: on this cluster, no conclusion
from a single 502-shaped failure. The repeat costs fifteen minutes.**

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

## The false lead (kept because it looked so convincing)

Runs 5-8 all died at the prefill→decode handover. From the exported pod logs (use
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

## The control experiment, and what it actually showed

`launch_device.py --mode reload --request request_config/sd_smoke/request.json --store
<our store>` — the kernel's own code, unmodified, our store, none of ours in the path:

    control 1 (03:45):  502 after ~14 min, no worker output
    control 2 (04:30):  PASS, evidence bundle downloaded and verified, 6 members

So the reload path **works on our store**, and the store is validated end to end by
upstream's own code. The failures cluster in time, not in mechanism.

Next session should start by re-running our own driver against a healthy cluster before
assuming any of the handover analysis holds. If it still dies at the handover, the
difference to chase is that the kernel runs BOTH phases as children of one
`cs_python launch.py` inside one `launcher.run()`, whereas we run prefill as a child of
the patched worker and decode IN-PROCESS in that same worker — creating an `SdkRuntime`
inside the appliance server process is the one structural difference the control does
not exercise.

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
4. **Unbounded retries (mine), twice.** Retrying `__IOP_INIT__` through ingress 502s is
   right, but I bounded it by `ready_timeout_s` (4200 s) — a budget that exists to cover
   a slow call that has NOT failed. Against a dead job it hammered a dead endpoint every
   5 s for an hour. I fixed that and thought the class was closed; it was not.
   `_wait_ping` had the same shape one function along, and spun ~30 min on a later run.
   Both now have their own budgets, and `_wait_ping` distinguishes "answered the wrong
   thing" (bring-up is slow -- wait the full budget) from "raised" (transport gone --
   180 s). **General rule: a retry budget belongs to the failure it retries, not to the
   operation's overall deadline. Reusing the deadline turns every dead endpoint into a
   silent hour.**

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
