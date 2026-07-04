# SpecDec-on-CS-3 roadmap (real kernels → PD serving + spec-dec rewind)

Handoff roadmap for continuing the WSE-3 draft-model work. Read
[[specdec-d2h-latency]] for the earlier backbone/latency phase. As of 2026-07-04.

## The two product paths (keep them separate)

- **Mode A — regular PD disaggregation serving.** Independent requests; each round re-ingests
  that request's own KV (the decode kernel's `NUM_ROUNDS` re-arm). NOT spec-dec.
- **Mode B — speculative decoding.** One request, KV ingested ONCE; across draft/verify rounds
  the decoder REWINDS to the last accepted position and continues (cache accumulates). This is
  the actual goal and needs a decode-position REWIND that upstream PR #13 lacked.

## DONE (validated)

- **PD framework** (merged `main`, PR #9): `driver_main --pd` brings up two pods (decode first,
  then prefill); KV crosses **pod-to-pod** via `kv_channel` (decode binds a `KvReceiver`, publishes
  `IOP_KV_BOUND`; prefill dials `IOP_KV_PEER`); the `appliance_handlers` factory seam
  (`_PREFILL_APP_FACTORY`/`_DECODE_APP_FACTORY`). Plug into this; do not reinvent.
- **Real-kernel PD adapters** (`realkv/pd_real_adapters.py`, on `lexu/specdec-real-kernels`): present
  the mock appliance interface, wrap the real qwen3 appliances + the A2 `kv_transform`, injected via
  `IOP_REAL_KERNELS=1`. **PD_REAL_SIM_PASS** (KV digest matched prefill==decode in simfab).
- **Single real appliances on real WSE-3, bit-exact, actual 28-layer size:**
  **DECODE_RESIDENT_DEV_PASS** + **PREFILL_RESIDENT_DEV_PASS** (`resident_device.py`).
- **Mode A saved** on branch `lexu/pd-disagg-modeA-serving`.
- **Mode B decode rewind — v1 (P-ALIGNED) validated bit-exact in simfab AND on real WSE-3:**
  `DECODE_REWIND_SIM_PASS` + on-chip MATCH (`rearm_all_identical=True`, 4380 tok/s). Committed on
  **`lexu/decode-rewind` in the WaferEngine repo** (`2d1c412` kernel + `73fa425` device cfg), built
  ON PR #13's decode (reuse `round_reset`/`rope_init_from_delta_p`; one `continuation` flag +
  cache-preserving `kv_ingress` gate + `rope_seek_continuation`). See [[pd-modeA-vs-modeB-specdec]].

## TODO (prioritized)

1. **v2 — token-granular decode rewind** (kernel, `lexu/decode-rewind`). v1 is P-aligned: re-arm
   position A must be a multiple of `P_BLOCK_SIZE` (8 sim / **256 device**) — too coarse for real
   `draft_len`≈16. v2 = per-PE non-uniform position (metainfo is already per-PE) + `A mod P`
   single-step RoPE-remainder rotations on top of `rope_seek_continuation`. This is the gating item
   for real spec-dec on device.
2. **Mode-B host adapter** (nc_service). The draft/verify loop: draft `draft_len`, accept K, rewind
   by R=`draft_len-K`, repeat, on ONE growing sequence. Needs (a) a kernel `n_steps = draft_len`
   per-round budget (today it generates "fill the cache," not a window), and (b) a decision on the
   **sampling/PRNG-on-rewind** behavior (does the sampler rewind with the position?). Wire onto the
   PD framework via the same `appliance_handlers` seam.
3. **Real-kernel PD device run (mode A / transport)** — re-run `run_e2e_pd_real.sh` with
   `READY_TIMEOUT=7200` + the send_x fix (#4) + ingress-502 hardening (#5) → `PD_REAL_DAEMON_DEV`.
   The data path itself is device-proven (prefill→transform→kv_channel→decode KV digest matched).
4. **send_x N-header fix** (`pd_real_adapters.DecodeRealAdapter`). Mode-A multi-round hangs because
   `send_x` sends a flat-zero X stream, MISSING the per-round **N-header tile** (decode
   `launch.py:2129`: X = `1 N-header (slot0=N) + (W-1) tokens`). Build the header, not zeros.
5. **Ingress-502 hardening** (framework `engine/io_pipeline/gateway/bridges.py`). Transient CS-3
   ingress 502s (HTML from `10.27.24.65:443`) at serve/teardown kill runs; catch `grpc.RpcError`
   and retry (see [[cs3-restore-grpc-502-gotcha]]). This blocked an otherwise-successful actual-size
   PD device run.
6. **Upstream coordination.** PR #13 is actively developed (recent commits = KV-transfer perf, no
   rewind). Rebase `lexu/decode-rewind` on the head periodically; consider upstreaming the rewind.

## Key facts for the next agent

- Branches: `lexu/specdec-real-kernels` (nc_service main dev), `lexu/pd-disagg-modeA-serving` (mode A),
  `lexu/decode-rewind` (WaferEngine repo — the rewind kernel). CLAUDE.md at the nc_service root has the
  architecture + build/test/device commands.
- Validate kernels GREEDY (`top_p=0`) vs a deterministic **logit** oracle — sampled tokens diverge on
  PRNG offset even when logits are bit-exact (this cost a long debugging detour; do not repeat).
- Sim gates: `cs_python` from `/home/lexu` (container binds both repos), `SINGULARITYENV_` prefix.
  Device: `/cs3-runner`, `csl` conda env, `CS3_HOST=CS-3-cmd` ControlMaster, `--ready-timeout` >
  compile (~40-60 min for 28 layers). See [[resident-real-kernel-device-validated]],
  [[pd-real-kernel-framework-seam]].
