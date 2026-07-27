# The `sd-pdSeparate` kernel IS the spec-dec target: it HAS in-kernel rewind, a clean `target.verify()` seam, and runs in the worker

Date: 2026-07-27 · Repo: `nc_service` (kernel in WaferEngine `CongjieHe/WaferEngine@cb49130f`, tag `pr-sd`)

**Project:** nc_service
**Author:** claude
**Status:** captured

## Situation

Continuing pdSeparate adoption. A **new** kernel dir appeared:
`models/qwen3_1p7b-sd-pdSeparate` (`sd` = spec-dec). This SUPERSEDES the earlier
conclusion in `topics/pdsep-kernel-adoption.md` that "the pdSeparate kernel is
mode-A, no internal rewind." That was true of `e2e-pdSeparate`; the **sd-**variant
is the spec-dec draft model and it **does** rewind. If you are about to build a
mode-A serve loop or an external re-arm for spec-dec, stop — use this kernel.

## What it is (device-VALIDATED)

`device_verdict.json` = PASS on CS-3/WSE-3, `artifact_mode: cached_reload`,
`sd_rearm` = two bit-identical decode rewind checks from one loaded artifact.
Self-contained host (`host/{specdec_protocol,specdec_runtime,kv_bridge,artifact_cache,hf_weights}.py`);
README states it "does not depend on or modify `waferengine/samples/specdec`."

- **In-kernel rewind.** "Device logically rewinds to `proposal_base_len +
  accepted_count`"; no KV SRAM cleared, RoPE / per-layer causal counts / step banks
  reconstructed from `cache_len`. The rewind API is the **8-word `uint32[8]` meta
  ABI** (magic `0x5344`, `MetaCommand.{LOAD_PREFIX, RESUME}`, `cache_len`,
  `accepted_count`, …) built by `pack_metadata()`. This REPLACES the old
  `kv_transform.repack_continuation_band` (slot1=accepted-pos) contract.
- **Clean integration seam:** `target.verify(DraftBatch) -> TargetFeedback`
  (currently `RandomTargetMock`). `DraftBatch.steps[DraftStep(token_id, q,
  topk_ids, topk_logits)]`, K in [1,16]. `TargetFeedback(accepted_count in [0,K],
  next_token)`. README: "Replacing the target mock requires implementing the same
  boundary; no device ABI change needed." → the nc_service GPU verifier plugs in here.
- **Decode output = top-K logits + q per proposal** (`[TOP_K bf16 logits | TOP_K
  int32 ids | sampled | q float32 | trailer]`), NOT dense logits — enough for p/q
  rejection sampling; `specdec_protocol.py` ships the exact acceptance + residual math.
  (This resolves the open "does the verifier need dense logits" question: no.)

## Non-obvious integration constraint: it runs IN THE WORKER

`cs_python launch.py / launch_decode.py -> serve_loop` runs on the **worker**
(login node runs `launch_device.py` csl-env / `StagedDispatch.run` ->
`SdkLauncher.run("cs_python launch.py …")` on the worker -> `subprocess` child).
`cs_python` only runs in the worker; the gateway/login-node has no serve path. So:

- `serve_loop` drives the wafer **in-process** (`runtime.send/receive`) — the
  in-process device-driving that nc_service's `InProcessPatchBridge` hotswap
  engineered is **native here**; do not re-implement it.
- BUT `target.verify()` ALSO runs in the worker, which is **network-isolated**
  (worker↔outside = L7 ingress :443; W→C is the constrained direction, per the
  `tcp_probe` work). So the `target.verify()` → external GPU verifier bridge MUST
  **relay out through the gateway** — nc_service's transport (gateway
  `ExchangePump`/`bridges.py`, `draft_service`/`verify_service`, `mock_verify_host`)
  is REQUIRED, not subsumed. Only the wafer-driving indirection is subsumed.
- **Control direction flips:** nc_service was *verify-drives* (GPU pushes
  `DraftAdvance` to a worker RPC executor). sd-pdSeparate is *draft-drives*
  (`serve_loop` owns the loop and pulls `target.verify()`).

## Lesson (cost two default flip-flops)

KV **layout** (strided vs chunk-major) and serving **semantic** (mode-A re-ingest
vs mode-B rewind) are **orthogonal** axes — do not conflate. The rewind kernel is
chunk-major layout + mode-B semantic. "Target is spec-dec / don't go mode-A" is the
semantic axis; "reference PR14" is the layout axis.

## Implications / next actions

- [ ] Fresh integration on a NEW branch off `main`; adopt the kernel's host driver
  (`specdec_runtime` + `specdec_protocol` + `kv_bridge` + `artifact_cache`) and
  bridge `target.verify()` (worker → gateway ingress → `verify_service` → GPU;
  `DraftBatch`/`TargetFeedback` ↔ `proto/`). Local `mock_verify_host` path first.
- [ ] Supersedes `topics/pdsep-kernel-adoption.md` "no rewind" for the spec-dec path
  (reconcile on next maintain).

## Pointers

- Kernel: `git -C /home/lexu/WaferEngine-staging show cb49130f:models/qwen3_1p7b-sd-pdSeparate/<path>` (tag `pr-sd`); read `README.md`, `host/specdec_protocol.py`, `host/specdec_runtime.py`, `host/artifact_cache.py`, `request_config/mtbench8/device_verdict.json`.
- nc_service branch `lexu/pdsep-kernel-adopt` (`dcc29a8`): `transform_chunk_major` is byte-identical to the kernel's `kv_bridge` (a validated cross-check; the kernel's kv_bridge is authoritative).
- Related: `topics/pdsep-kernel-adoption.md`, `inbox/2026-07-21-pdsep-kv-contract-adopt.md`, `inbox/2026-07-21-cs3-elf-extract-reload-scale.md`, `topics/specdec-modeb-drive-path.md`.
