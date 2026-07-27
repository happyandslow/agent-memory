# Wiring the kernel's `target.verify()` out of the worker: the live transport is an in-process gRPC hotswap, not FIFO — and that dictates the whole protocol

Date: 2026-07-27 · Repo: `nc_service`, branch `lexu/pdsep-kernel-integration`

**Project:** nc_service
**Author:** claude
**Status:** captured

## The situation this applies to

You are bridging the `sd-pdSeparate` kernel's `target.verify(DraftBatch) -> TargetFeedback`
seam out of the network-isolated worker to the GPU verifier, and you need to know what the
existing nc_service transport actually is before designing the wire format. Reading
`executor/fifo_server.py` and `gateway/bridges.py::LauncherBridge` will lead you to build on
`mkfifo` + `daemon_cmd` + poll-for-READY. **That path is legacy.** Designing against it
produces a protocol with the wrong constraints in both directions.

## The live path (Le's correction, then code-verified)

It is `InProcessPatchBridge` — an in-process hotswap of the worker's own gRPC server.
`driver_main.py:216-222` forces both `--pd` roles onto the in-proc path. The controller finds
the stock `sdk_appliance_server.py` and its `:9000` listener on the pod, reads the real
environment out of `/proc/<pid>/environ`, **text-swaps the bodies** of `sdk_run_command` /
`sdk_download_files` (the coordinator filters unknown method names, so only body replacement
works — you cannot add a method), `SIGSTOP`s the parent and `SIGTERM`s the listener child, then
relaunches the patched server with the original argv+env. After that each frame is
`launcher.run(frame)` → `handler.handle_run_command` → `serve_core.serve_one`.

Three consequences that shape the design, none obvious from the seam itself:

- **`handle_run_command` holds a module-level `_LOCK` for its entire duration.** A blocked
  handler blocks even a ping. Long-polling with a bounded budget is therefore mandatory, not a
  refinement.
- **The ~150 s `runtime.load()` sits in `__IOP_INIT__`, not on the exchange path**
  (`run_e2e_pd_real.sh` already carries `READY_TIMEOUT=4200` for the compile+init window). So a
  serve thread can be started in `build_handlers` and block there until the wafer is ready.
- **There is no shell and no FIFO.** Frames are gRPC string fields, so `MAX_ARG_STRLEN` and
  `PIPE_BUF` — both of which would otherwise force bf16 bit-packing of the top-K logits —
  simply do not apply.

## Two more corrections worth carrying

**KV format needs no change, and the handoff is already serialized.** Both sides' intermediate
representation is the same: `(inj_xk, inj_xv)`, chunk-major, decode's native inj layout
`(P_Y, P_BLOCK_SIZE, (Pw+2)*kv_words_per_pe)` uint16. Our `transform_chunk_major` was a port of
the kernel's `kv_bridge`, and `test_kv_chunk_major.py` pins byte equality for clpp ∈ {1,2,4}.
The kernel's current handoff already does `np.savez` — to `inj_{i}.npz` files, not to a socket
— and `pdsep_proto/kv_handoff_codec.py` is already `np.savez` into a `BytesIO` ("the .npz
payload, on the wire instead of on disk"). **The delta is file→socket, not "add serialization."**
Volume is the real cost: roughly 114 KB/token, so ~3 MB for an mtbench8 prompt and ~940 MB at
8k `[unverified — arithmetic estimate, not measured]`.

**Control-plane metadata should NOT be routed through the gateway** (Le's correction, conceded).
The existing `_frame_blob` header `[MAGIC, n_bytes, first_token]` already ships the first token
alongside the KV; adding a separate `VERB_SD_START` only existed to dodge `serve_loop:109-110`
materializing `PREFILL_LENS`/`token_ids` early, which is not worth a second path.

## Protocol invariants the exchange layer imposes

These are what the wire format and the rendezvous have to satisfy; each was read off the code.

- **Bounded blocking is not optional.** `ExchangePump` does not retry on timeout — it calls
  `bridge.on_hang()`, which raises and kills the SdkLauncher session. The worker must never wait
  longer than the gateway, so the handler returns a `PENDING` frame instead of over-waiting, and
  the gateway sends its own budget (`block_ms`) down.
- **The idempotency key must live in the payload.** `serve_core.serve_one` hands the handler
  only the payload, never a sequence number; and on a handler exception it returns
  `(ERR_SEQ, VERB_ERR, [])` *without* updating the replay cache, so the pump resends. Under
  long-polling every retry is a new seq carrying the same feedback, so the replay cache cannot
  dedupe it. The only workable key is an `(request_idx, round_id)` ack carried in the frame —
  which is self-clocking: feedback for round R *is* proof the gateway received batch R.
- **Never encode an empty reply.** `ExchangePump` treats an empty u32 list as a reply mismatch
  and retries, so any "empty means done" encoding livelocks. Every upstream frame carries an
  8-word header.
- **Request boundaries are invisible.** `serve_loop`'s inner loop breaks on EOS / max_new_tokens
  / cache envelope *without* calling `verify()` again, and emits no DONE between requests. The
  gateway can only detect that a request ended by watching `request_idx` increment.

## Implementation rule this produced (a real bug, reproduced then fixed)

**Encode before mutating state.** `encode_batch` can throw (bf16 tripwire, ragged top-K). With
`_pending = item` set before the encode, a throw left `_pending` set and `_last_reply` still
`None`, so the next retry did `list(None)` → `TypeError` escaping the handler. Worse, the batch
was already dequeued and could never be acked, so the producer would block on `fb_q` forever and
the gateway would see endless `PENDING`. Fix: encode first, mutate after, and turn an
unencodable batch into a terminal `ERROR` rather than a hang.

**Promotion candidate (procedural).** Stated without this project: *before designing a protocol
on top of an existing transport, verify which transport is actually live — a legacy path left in
the tree will hand you the wrong constraint set in both directions (phantom limits like
`PIPE_BUF`, missing limits like "the handler holds a global lock").*

## Implications / next actions

- [ ] Tasks 1–3 landed (vendor snapshot `5b86c0f`, `wire.py`, `rendezvous.py`); the remaining
      work is the target adapter and the gateway side.
- [ ] Measure the KV volume per token for real — the ~114 KB/token figure is unmeasured and the
      8k number rests on it.

## Pointers

- `waferengine/samples/specdec/sd_kernel/{wire.py,rendezvous.py}` — the contract and the
  rendezvous state machine; both carry these invariants in their module docstrings.
- `docs/superpowers/plans/2026-07-27-sd-pdsep-kernel-integration.md` — the task breakdown.
- Related: `inbox/2026-07-27-sd-pdseparate-specdec-kernel.md` (what the kernel is — note its
  "relay out through the gateway" line refers to the *data* path; the control plane does not),
  `topics/specdec-modeb-drive-path.md`, `topics/pdsep-kernel-adoption.md`.
