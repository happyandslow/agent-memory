# Driving a vendored kernel's host loop from an RPC handler: it has no "run one round" API, so you patch its target seam, not its launcher

Date: 2026-07-27 · Repo: `nc_service`, branch `lexu/pdsep-kernel-integration`

**Project:** nc_service
**Author:** claude
**Status:** drained

## The situation this applies to

You have vendored a kernel that ships its own complete host serve loop, and you need to
drive it **round by round** from an io_pipeline handler (one gateway `launcher.run(frame)`
= one round). The obvious move is to have the handler call the kernel's launcher directly:
`handler(frame) -> kernel.do_one_round() -> batch`. You go looking for that entry point.

**It does not exist, and the reason it does not exist is structural, not an oversight.**

Symptom you would hit instead: you start reading `launch_decode.py` for something at round
granularity, find only `build()` / `serve()` / `run()`, and are tempted to either (a) call
`SdkRuntime.send/receive` yourself from the handler, or (b) fork the serve loop into a
resumable state machine. Both are the same mistake wearing different clothes.

## Why the arrow does not exist: the kernel is control-inverted

`sd-pdSeparate`'s entry points bottom out in one blocking driver:

    launch_decode.serve(cfg) -> run(...) -> SdkRuntime.load() -> serve_loop(...)   # blocks
                                                                 until ALL requests done

`serve_loop` is a `for request in requests: while True:` that owns the entire request
lifecycle. Per round it does: KV npz load, `send_kv_command` across 4 bands, host-token
send, `receive_batch` (N records + a TSC burst), `resume_after_feedback` rewind arithmetic,
the all-accepted replay (`forward_steps=K+1, emit_skip=1`), the cache-envelope guard, the
committed ledger, EOS / `max_new_tokens` policy, and the verdict JSON.

**Exactly one statement in that loop yields control: `feedback = target.verify(batch)`.**
Everything else is state the kernel owns. It is a driver, not a library — it wants to call
you, not be called.

## The three options, and the cost accounting that settles it

    (A) rewrite serve_loop into a resumable state machine
        handler(frame) -> kernel_step(state) -> (new state, batch)
        X  requires editing a read-only vendored tree, or forking it
        X  re-align on every upstream revision

    (B) handler owns SdkRuntime and calls send/receive itself
        X  must reimplement ~200 lines of protocol state machine
        X  this is literally what model_adapter/ already is: 4,377 lines,
           the debt this whole integration exists to retire

    (C) run serve_loop verbatim on a thread; intercept at its one yield point
        OK  install_bridge_target: rebind specdec_runtime.RandomTargetMock

Ledger:

| | we maintain | kernel gives us |
|---|---|---|
| (B) | meta packing + rewind arithmetic + replay/emit_skip + repack + record parse + ledger + EOS policy + envelope guard (~200 lines, drifts) | `runtime.send/receive` |
| (C) | one attribute assignment + two queues (`rendezvous.py`, 249 lines, kernel-agnostic) | all of the above, byte-identical, sha256-pinned |

The target seam is the right interception point because **the kernel designed it to be
replaced**: its README says "Replacing the target mock requires implementing the same
`verify(DraftBatch) -> TargetFeedback` boundary; no device ABI change is needed."

## The thread is for a stack, not for concurrency

A blocking driver needs somewhere to *stand* while it waits for `verify()` to return. Both
ends of the rendezvous block, so exactly one side runs at any instant — concurrency risk is
nil. The complexity in `rendezvous.py` is entirely about the gateway's retry semantics
(`serve_core`'s at-least-once path), not about threading.

## Two things called "in-process patch" that are NOT the same mechanism

Easy to conflate, and conflating them makes the risk assessment wrong.

|  | `InProcessPatchBridge` (backbone, pre-existing) | `bridge_target` (this work) |
|---|---|---|
| layer | transport, leg-② gateway↔worker | application, inside the worker process |
| patches | Cerebras's own `sdk_appliance_server.py` | our vendored `specdec_runtime.RandomTargetMock` |
| how | **textual re-body** of two methods + **process relaunch** (SIGSTOP parent, SIGTERM `:9000` listener, relaunch with original argv/env) | **one attribute assignment** |
| undo | restore sentinel -> controller relaunches stock server | `undo()` closure |
| risk | third-party file, needs watchdog + restore, coupled to cluster layout | a name in a tree we vendored; no restart, no restore machinery |

They **compose one-way**: `bridge_target` is installed by `build_handlers`, which only runs
because `InProcessPatchBridge`'s patch already took effect. But `bridge_target` is
transport-agnostic — it works unchanged under the legacy FIFO `LauncherBridge`, since both
transports share `serve_core.serve_one` and the same `build_handlers` seam.

    gateway: launcher.run("<seq><verb><hex>")
       |
       v  <-- InProcessPatchBridge's patch takes effect here
    handle_run_command()                       [holds module-level _LOCK]
      +- _ensure() -> IOP_BUILD_HANDLERS dotted path
      |    +- build_sd_decode_handlers()
      |         +- install_bridge_target(...)  <-- bridge_target's patch here
      |         +- start serve thread -> serve_loop -> target.verify() parks
      |         +- return {VERB_SD_EXCH: StepHandler}
      +- serve_one(frame, handlers) -> StepHandler -> rendezvous -> verify() wakes

## The one real cross-layer interaction

`handle_run_command` holds a module-level `_LOCK` for the whole call, and our `StepHandler`
long-polls *inside* it. So a blocked worker blocks even `__IOP_PING__`. That is the
mechanical reason `block_ms` must stay under `deadline_s`: they are not two independent
timeouts, they are two ends of the same serialization point.

## Silent-failure mode this design has, and the guard for it

The patch works **only because** `serve_loop` looks the name up in its own module globals
(`from host.specdec_protocol import RandomTargetMock`). If upstream ever switched to a
qualified call `specdec_protocol.RandomTargetMock(...)`, rebinding would be a **no-op** and
the run would quietly fall back to the RANDOM mock — batches still flow, tokens still
commit, output is garbage. Guarded by
`test_bridge_target.py::test_patch_target_exists_on_the_REAL_serve_loop_module`, which
asserts both halves (name present in the module, source does not use a qualified call).

**Promotion candidate (procedural).** Stated without this project: *when a vendored
component ships a blocking driver loop rather than a per-step API, do not fork it and do not
reimplement its inner loop — find the one place it yields control (usually a callback or
strategy object it was designed to let you replace), run it on a thread, and rendezvous
there. Then guard the interception point with a test that fails loudly if upstream changes
how it resolves that name, because a missed monkeypatch fails silently and plausibly.*

## Pointers

- `waferengine/samples/specdec/sd_kernel/bridge_target.py` — the injection; module docstring
  carries the "why this name binding" argument.
- `waferengine/samples/specdec/sd_kernel/rendezvous.py` — the two queues + the ack-clocked
  idempotent handler.
- `docs/superpowers/plans/2026-07-27-sd-pdsep-kernel-integration.md` — task breakdown and
  the retire/reuse code inventory (12,895 lines of `samples/specdec`, ~5,400 retired).
- Related: `inbox/2026-07-27-inproc-exchange-constrains-verify-seam.md` (the transport and
  the protocol invariants it forces), `inbox/2026-07-27-sd-pdseparate-specdec-kernel.md`
  (what the kernel is).
