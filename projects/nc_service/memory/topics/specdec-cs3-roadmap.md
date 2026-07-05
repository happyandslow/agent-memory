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
- **Mode B decode rewind — v2 (TOKEN-GRANULAR) validated bit-exact in simfab AND on real WSE-3
  (2026-07-04):** `DECODE_REWIND_V2_SIM_PASS` — re-arm at an ARBITRARY accepted position A (not
  P-aligned), which real `draft_len`~16 needs. Sim `PREFILL_LENS=[8,8,16,13]`: A=13 (non-aligned)
  MATCH + A=8/16 (v1 P-aligned regression) MATCH; KV-SEED PASS. **DEVICE PASS** on real WSE-3
  (`test_device_2x2block_specdec.json` PREFILL_LENS=`[256,272,512]`, 28 layers, P_BLOCK_SIZE=256):
  A=272 (non-aligned v2) MATCH `DECODE_REWIND_V2_SIM_PASS` + A=512 (v1 regression) MATCH — top-k
  logit oracle values==/indices== on chip (compile 35.8s, run 13.5s; `rearm_all_identical=None` =
  device has no read_symbol, oracle is the proof). Committed `c3cf113` (kernel+host+cfg) + spec
  `9978b5f` on `lexu/decode-rewind`; baseline tag `decode-rewind-v2-start`. Mechanism: per-PE
  iter_num staircase (`q+1/q`, already
  the steady state — only PE `step%P` writes/advances iter_num) + uniform `n_steps=kv_len*P - A`
  (from A, NOT per-PE iter_num, or the round barrier deadlocks) + RoPE seek to exact A (base delta_P
  + `A-base*P` singles incl. the A%P remainder) + `step=A%P`. Carrier: 1-u32 meta `[iter_num:lo16 |
  A:hi16]`, A!=0 <=> continuation (no meta widening; relay files boolean `cont` unchanged).

## TODO (prioritized)

1. **v2 — token-granular decode rewind** (kernel, `lexu/decode-rewind`). ✅✅ DONE — SIM + DEVICE
   both bit-exact (`DECODE_REWIND_V2_SIM_PASS`, committed `c3cf113`; device MATCH on real WSE-3, see
   DONE section). Was: v1 P-aligned (too coarse for `draft_len`≈16). **Item #2 (mode-B host adapter)
   is now UNBLOCKED** — the token-granular kernel re-arm it needs exists and is device-proven. (Also
   worth: periodic rebase of `lexu/decode-rewind` vs PR#13 head — item #6.)
2. **Mode-B host adapter** (nc_service). ✅ FIRST INCREMENT DONE (2026-07-04) — SIM + DEVICE.
   `MODEB_SIM_PASS` (nc_service `e9a1fe0`): the adapter (`realkv/modeb_adapter.DecodeModeBAdapter`)
   drives the real rewind kernel as a chained draft-window loop — window 0 full-ingress the prefill
   KV, window r>0 continuation re-arm at the growing accepted position, seeding from the previous
   window's last token (the chain launch.py's static schedule can't do). 4 windows reproduce a
   STRAIGHT decode bit-exact (top-k logit oracle, greedy). Foundation piece: a kernel draft-window
   budget `STEPS_PER_ROUND` (WaferEngine `a82fbf9`, `DECODE_WINDOW_SIM_PASS` + byte-identical off) +
   `repack_continuation_band` in kv_transform + the send_x seed fix (W_E-embedded resume token, not
   zeros). DEVICE: `test_device_2x2block_window.json` (28L, P=256, greedy) re-armed @264/@260
   (non-aligned) MATCH on real WSE-3 (`85ff8e0`) — the mode-B kernel capability works on hardware.
   Spec `docs/superpowers/specs/2026-07-04-modeb-host-adapter-design.md` (local, gitignored).
   **REMAINING mode-B follow-ups:** (a) partial-accept correction — ✅ DONE (`5b1737d`). Root cause:
   `cached_len += k` dropped the correction's position (off by one); fix `+= k + len(corr)`, seed =
   last correction (or k-th accepted draft). Definitional (confirmed = accepted + corrections);
   discriminating SDK-free unit test `test_modeb_accounting` (old=17, fixed=18); `MODEB_PARTIAL_SIM_PASS`
   (no-op-correction sim confirms the kernel re-arm/overwrite at partial positions 18/21/23 — but toy
   weights emit a degenerate token so the sim can't discriminate the accounting, the unit test does).
   (b) ✅ DONE — full ADAPTER-chain on device: `MODEB_DEV_PASS` on real WSE-3 (nc_service `2ca25e2`
   `modeb_device.py` launcher, WaferEngine cfg `fa8de58`). The adapter drove 16 draft windows
   re-armed at token-granular positions 272/288/.../496, each reproducing the straight decode bit-
   exact (top-k logit oracle, real 28L/P=256/full-vocab, greedy) — 256 tokens 0 mismatched. Gateway
   flaky: warm auth (`cs3-ssh.sh CS-3`) IMMEDIATELY before `cs3-run.sh` (short grace window; cs3-run
   doesn't auto-feed TOTP). Was: full ADAPTER-chain on device — needs a device launcher like
   `resident_device.py`; the window run above proved the kernel, `DECODE_RESIDENT_DEV_PASS` proved the
   adapter drive pattern, but not both together. (c) CONNECT to the real GPU verify loop.
   IMPORTANT (reviewed PR#9 "PD disaggregation" — the LAST PR): the whole loop is ALREADY wired +
   mock-tested. `driver_main --pd`+`pd_rendezvous` = the prefill→decode transition (KV pod-to-pod via
   kv_channel); `run_session` (gateway_frontend) = the GPU↔engine loop (dial verify svc → per cmd
   translate → route prefill vs decode → exchange via pump → build_response); `build_decode_handlers`
   loads KV ONCE then exchange_batch per round (= mode-B sequencing); `mock_verify_host` = the GPU.
   NOT pending: loop / prefill→decode / protocol. PENDING:
   (i) ✅ DONE (`7bf868b`) — `register_modeb_factories` twin + `IOP_SPECDEC_MODE=B` dispatch in
   build_handlers points `_DECODE_APP_FACTORY` at `DecodeModeBAdapter` (prefill unchanged); SDK-free
   seam tests. (ii) ✅ DONE (`1b3238f`) — the adapter is structurally correct for the framework: the
   prefill handler returns a THROWAWAY mock draft (content irrelevant to verify), so the decode's
   FIRST exchange_batch full-ingests KV + drafts window 0 from prefill_len IGNORING the request
   accounting (= prefill's mock), and later exchanges continue via `cached_len += k + len(corr)` from
   the request (which refers to the decode's own windows). Added last_blobs + a cache-bound guard;
   `MODEB_EXCH_SIM_PASS` drives the real kernel through exchange_batch with codec requests → reproduces
   a straight decode bit-exact. (iii) IN PROGRESS: full loop runner BUILT
   (`818ca05` `run_e2e_pd_modeb_sim.sh` = sim variant of run_e2e_pd_real.sh: driver_main --pd +
   mock_verify_host + 2 cs_python simfab workers, decode on the rewind adapter via IOP_SPECDEC_MODE=B,
   proven test_sim_2x4 prefill+decode pair). ENV FINDING: must run on CS-3 in the `csl` conda env —
   the full-loop driver needs `cerebras.sdk.client` (SdkLauncher, used by InProcessPatchBridge);
   cs_python's container has SdkLayout/SdkRuntime+grpc but NOT SdkLauncher, and there is no local csl
   env. NOT YET RUN: EIDF gateway intermittently rejecting auth (repeated Permission denied at cs3-run
   connect — cs3-run DOES use cs3-ssh auto-TOTP transport, so it's the flaky gateway itself; retry when
   it cooperates). Then partial-accept on device, then the real GPU verify service. Success =
   mock_verify_host "failures:0". Run: on CS-3 login node, `conda activate csl` +
   `IOP_REAL_KERNELS_SRC_{PREFILL,DECODE}=~/rsync/qwen3_1p7b-{prefill,decode}-rsync bash
   waferengine/samples/specdec/realkv/run_e2e_pd_modeb_sim.sh 2`. (d) sampling-on-a-rewind policy — a SERVING-LAYER decision
   (temperature/top_p are per-request, currently baked at compile in ht_tail.csl:42-44); the greedy
   gate deliberately factors it out (logits don't depend on sampling). Below is the ORIGINAL context:
   **IMPORTANT — the loop itself is NOT from
   scratch:** the merged PR #9 already implements and TESTS the full spec-dec draft/verify/accept-K/
   correction LOOP — but against the **MOCK/passthrough** kernel (`pd_worker.py` drives per-round
   `codec.encode_request_payload(has_commit, has_proposal, num_accepted, correction_ids)` →
   `DecodeAppliance.exchange_batch`; the mock echoes, it does NOT rewind KV). So the host accounting
   (num_accepted, correction_ids, draft_len, per-round iteration) is validated WITHOUT a real kernel;
   the piece that was missing — the actual KV rewind in the real decode kernel — is now built (v1).
   Mode B = **connect that tested loop to the real rewind kernel**, plus (a) a kernel
   `n_steps = draft_len` per-round budget (today it generates "fill the cache," not a `draft_len`
   window), and (b) a decision on the **sampling/PRNG-on-rewind** behavior (does the sampler rewind
   with the position?). Wire via the same `appliance_handlers` seam.
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
