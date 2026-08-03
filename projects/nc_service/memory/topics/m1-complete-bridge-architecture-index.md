---
summary: M1 done — the sd-pdSeparate bridge runs end to end with no SDK, no wafer, no GPU — plus an index of which module runs where
tags: [nc_service, drained-inbox, 2026-07-28]
---

# M1 done: the sd-pdSeparate bridge runs end to end with no SDK, no wafer, no GPU — plus an index of which module runs where

This topic was created by the 2026-08-03 maintain pass from a dated inbox capture. Keep it as the durable, topic-scoped home for the finding; the original capture is marked drained.

## Drained capture — 2026-07-28

Source: `memory/inbox/2026-07-28-m1-complete-bridge-architecture-index.md`

# M1 done: the sd-pdSeparate bridge runs end to end with no SDK, no wafer, no GPU — plus an index of which module runs where

Date: 2026-07-28 · Repo: `nc_service`, branch `lexu/pdsep-kernel-integration`

**Project:** nc_service
**Author:** claude
**Status:** captured

## The situation this applies to

You are picking up the sd-pdSeparate integration and need to know (a) what already
works, (b) **which of the ~10 new modules runs on which machine** — because the three
components (GPU host / CS-3 gateway node / CS-3 worker pod) do NOT share a filesystem,
a Python env, or a network direction, and putting a module on the wrong side is the
mistake that costs a device slot to discover.

## What M1 established (executable, not argued)

> The draft tokens a **byte-identical** `serve_loop` produces satisfy **all eight**
> checks the real SGLang client performs — reproducible with no Cerebras SDK, no
> wafer, and no GPU.

`sd_kernel` 140 tests, full suite 495 passed / 2 skipped, three consecutive clean runs.
11 tasks; every one gated on a failing test first, most closed with a mutation test.

## The architecture index — which module runs where

Three machines, no shared FS, and the network direction is client-dials-outward from
the gateway in BOTH directions.

```
  GPU host (target)              CS-3 gateway node              CS-3 worker pod            WSE-3
  ================               =================              ===============            =====
  DraftControl gRPC SERVER  <--(1)--  gRPC CLIENT                                     
  (SGLang REMOTE_STANDALONE                |                                          
   or mock_verify_host)                    |  launcher.run(frame)                     
                                           +-----------(2)-------->  patched RPC handler
                                                                            |
                                                                     serve_core.serve_one
                                                                            |
                                                                     REAL serve_loop  --(3)--> kernel
```

| module | runs on | role |
|---|---|---|
| `sglang_shapes.py` | **GPU side** | mirror of SGLang's request construction + its 8 response checks |
| `mock_verify_host.py` | **GPU side** | local stand-in; `--shape sglang` drives the real shapes |
| `gateway_frontend.py` | gateway | gRPC client session loop; `advance_fn=` is the protocol seam |
| `sd_gateway.py` | gateway | leg-1 <-> leg-2 for SD; owns the ack state and **seq allocation** |
| `translate.py` | gateway | proto <-> v1 payload; its `build_response` is reused verbatim by SD |
| **`wire.py`** | **BOTH gateway and worker** | the leg-2 contract — the only module that must exist on both sides |
| `rendezvous.py` | worker | the two queues + the ack-clocked idempotent handler |
| `bridge_target.py` | worker | the monkeypatch that redirects `target.verify()` |
| `handlers.py` | worker | the `build_handlers` seam; starts the serve thread |
| `kernel_env.py` | worker | locate / import the vendored kernel; fake vs real serve scalars |
| `fake_device.py` | **tests only** | stands in for SdkRuntime **plus the wafer** |
| `targets.py` | (unused by M1) | Task 7; superseded — SGLang *is* the target |

Kernel modules we now depend on instead of reimplementing:

| kernel module | runs on | note |
|---|---|---|
| `host/specdec_runtime.py::serve_loop` | worker | **byte-identical**, sha256-pinned |
| `host/specdec_protocol.py` | worker | `TargetFeedback` / `DraftBatch` / the 8-word meta ABI |
| `launch_decode.py` | worker (M2) | owns SdkLayout / SdkRuntime / load / run |
| `host/kv_bridge.py` | (M4) | prefill egress -> decode ingress transform |

**The index fact that matters most:** `wire.py` is the ONLY module needed on both sides
of leg-2. Everything else is single-sided. A module that "seems useful on both" is a
design smell — `targets.py` was exactly that mistake (defined on `wire.BatchMsg`, a
leg-2 type, while the GPU only ever sees the leg-1 `Proposal`).

## Where the seams are, and why each is there

- **`gateway_frontend(advance_fn=)`** — a protocol whose leg-2 exchange is not 1:1 with a
  gRPC command needs its own seq allocation. Default `None` keeps v1 byte-identical.
- **`IOP_BUILD_HANDLERS` -> `handlers.build_sd_decode_handlers`** — the backbone never
  imports a sample; the worker resolves our handler by dotted path.
- **`serve_runner=`** — the fake/real device switch. The injection POINT is production
  code; the fake implementation lives in `fake_device.py` so `handlers.py` never imports
  a fake (pinned by a test that parses handlers.py's AST import graph, not its text —
  the docstring mentions `fake_device` on purpose).
- **`RandomTargetMock` rebinding** — the kernel's only yield point. See
  [[2026-07-27-why-patch-the-target-not-the-launcher]].

## The three M1 scope limits, each pinned by a test

1. **The prompt does not travel on leg-2.** `serve_loop` materialises
   `PREFILL_LENS`/`token_ids` eagerly, so the wafer's prompt is staged in cfg and the
   prefill command's `emitted_ids` never reach the worker. Dynamic prompts need a second
   inversion on the prefill phase.
2. **The distribution stops at the gateway.** Every step carries `q` + top-K over leg-2,
   but leg-1's `Proposal` has only `draft_ids`. Not an oversight — SGLang verifies
   target-only. See [[2026-07-28-sglang-already-speaks-our-protocol]].
3. **One request per daemon lifetime** (N=1). Multi-request needs the prefill side too.

## Two bugs found by writing the tests first

- **`encode_batch` can raise after the batch left the queue.** With `_pending = item` set
  before the encode, a throw left `_pending` set and `_last_reply` `None`, so the retry
  did `list(None)`. Worse: the batch was unackable for ever, so the producer blocked on
  `fb_q` and the gateway saw endless PENDING. Fix: encode first, mutate after, and turn an
  unencodable batch into a terminal ERROR.
- **A 1-in-20 flaky in the gate itself.** `max_rounds` let the CLIENT tear the stream down
  while the server was still blocked reading the final reply, so the last round's
  bookkeeping raced. Fix: let the SERVER drive teardown — which is also the real
  interaction shape (SGLang's docs say not to set `--max-rounds` for serving). Verified
  0/30 and 0/15 after.

**Procedural, worth keeping:** when a test asserts "X happened", make it also assert the
condition that would make X vacuous. The PENDING test asserts `bridge.exchanges > rounds`
("no PENDING poll happened; the test did not exercise what it claims"); the prompt-scope
test asserts the two prompts differ ("make them differ, or this test proves nothing").

## Implications / next actions

- M2 = swap `fake_device` for the real `launch_decode.serve()` on CS-3. **Its first
  deliverable is re-measuring the baseline**, not verifying old numbers: 655 us/token is a
  long-form autoregressive workload measured inside the kernel's own loop (no gateway);
  leg-2 4.5 ms was the OLD kernel including its handler's work; RDMA 12.3 GB/s used the
  old KV sizes/layout.
- M2 does **not** need PD two-pod: the kernel's own `launch.py` does prefill -> kv_bridge
  -> decode in ONE worker and is device-validated. Using two pods costs an extra
  allocation and an extra network hop, polluting the baseline.
- [ ] Still blocked on SGLang: batch size (their `batch_advance` is concurrent, we are
      one-in-flight end to end). **`draft_len` 4 vs 16 is CLOSED** (2026-07-29): measured
      on the real WSE-3, k=16 is our preferred point too (2.8x cheaper per draft token),
      and `MAX_DRAFT_LEN == 16` is a hard kernel assert, not a config knob. See
      [[2026-08-02-cerebras-nvidia-bridging-open-items-audit]].

## Pointers

- `docs/superpowers/plans/2026-07-27-sd-pdsep-kernel-integration.md` — the 11-task plan
  (gitignored working doc), milestones M1-M4, and the "re-measure the baseline" table.
- `waferengine/samples/specdec/sd_kernel/tests/test_m1_gate.py` — the gate itself.
- ContextBase: *sd-pdSeparate bridge: M1 complete + module/component index*.
- Related: [[2026-07-27-why-patch-the-target-not-the-launcher]],
  [[2026-07-27-inproc-exchange-constrains-verify-seam]],
  [[2026-07-28-sglang-already-speaks-our-protocol]].
