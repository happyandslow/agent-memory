---
summary: Mode-B (spec-dec rewind) per-round drive path with file:line annotations + timing anchors — where a ~115ms recurring round actually spends its time.
tags: [nc-service, specdec, mode-B, latency, drive-path, wse3, profiling]
---

# Mode-B per-round drive path + timing anchors

Companion to [specdec-d2h-latency](specdec-d2h-latency.md). That note has the measured numbers; this one is the annotated **call path** so a profile line maps to exact source.

## Summary

Device fact: decode kernel = **2240 tok/s = 446 us/tok**, so a `draft_len=16` window is only **~7 ms of fabric**. A measured recurring (rewind) round is **~115 ms** => **~108 ms is host/transport overhead, not compute**. This maps where it goes.

## Two nested timing scopes

```
gateway_frontend.run_session                         [gateway_frontend.py:119]  -- driver clock = "driver rtt"
  target.exchange(seq, u32s)
    |- ExchangePump.exchange -> InProcessPatchBridge.run_exchange(frame)
         |- launcher.run(frame)          == TRANSPORT: gRPC driver -> worker/pod ==
              |- (worker) patched sdk_run_command -> build_decode_handlers
                   |- adapter.exchange_batch(ingress)  [modeb_adapter.py:219]
                        |- draft_window(...)           [modeb_adapter.py:163]  -- "worker total" (t0..end)
```

`transport = driver_rtt - worker_total`. **`worker_total` is the appliance<->wafer ring only** — it does NOT include the `launcher.run` gRPC hop.

## `draft_window` — anchors + the real call chain each wraps

```python
def draft_window(self, rearm_A, seed_tokens):          # modeb_adapter.py:163
    t0 = _pc()                                          # -- worker_total start

    # -- band_build ---------------------------------- modeb_adapter.py:181-185
    band  = repack_continuation_band(self._d, A)        # kv_transform.py:394  META-ONLY, NO KV (~P*Pw u32, ~1 KB)
    bands = [band] * P_Y                                #   round 0 instead uses self._full_bands (~29 MB REAL KV)

    # -- band_send ----------------------------------- modeb_adapter.py:187-189
    for by in range(P_Y):                               #   P_Y = 4
        send_kv_band(by, bands[by])                     # appliance_real.py:227
        #  |- list(int(x) for x in band_u32)            # appliance_real.py:229   <- Python per-element int()
        #  |- sess.send(list, stream=f"kv_band_{by}")   # appliance_session.py:73
        #       |- buf = np.asarray(u32s,u32).copy()    # appliance_session.py:74  <- RE-numpy the list (2nd convert)
        #       |- rt.send(stream, buf, nonblock=False) # appliance_session.py:75  <- BLOCKING H2D -> wafer

    # -- x_build ------------------------------------- modeb_adapter.py:191
    xseed = self._x_seed_from_tokens(seed_tokens)       # modeb_adapter.py:134  (numpy embed gather, bf16->u32)

    # -- x_send -------------------------------------- modeb_adapter.py:192
    send_x(xseed)                                       # appliance_real.py:231 -> sess.send (blocking H2D)

    # -- recv16 -------------------------------------- modeb_adapter.py:196-199
    for _s in range(self._draft_len):                   #   draft_len = 16
        recv_logits_step(self._S)                       # appliance_real.py:235
        #  |- sess.receive(n, stream="out")             # appliance_session.py:77
        #       |- blob = np.empty(n, u32)              # appliance_session.py:78
        #       |- rt.receive(stream, blob, n,          # appliance_session.py:79  <- BLOCKING D2H, once PER STEP
        #                    nonblock=False)

    # -- tsc ----------------------------------------- modeb_adapter.py:200
    recv_tsc()                                          # appliance_real.py:239 -> sess.receive(8) blocking
```

Wire itself = `SdkRuntime.send/receive`, `memcpy_required=False` direct streams (`appliance_session.py:67`), worker<->WSE — the "appliance ring" the d2h memo measured at ~0.166 ms for a passthrough kernel.

## What `send_kv_band` carries (kills the "re-upload KV every round" theory)

| round | builder | content | size |
| --- | --- | --- | --- |
| **0** (`rearm_A is None`) | `repack_kv_band(inj_xk,inj_xv,...)` (`kv_transform.py:367`) | the **real K/V cache** — one-time resident ingest | **~29 MB** |
| **>=1** (continuation) | `repack_continuation_band(d,A)` (`kv_transform.py:394`, **no KV args**) | **meta only**: P*Pw tiles of `[iter_ly_staircase, A]`; kernel gates on `A!=0` to rewind + keep resident KV | **~1 KB** |

`send_kv_band` is just the transport primitive (push a band on `kv_band_{by}`); the kernel's per-round protocol always reads a band, but on rewind rounds it's a ~1 KB control message, not the cache. So `band_send` on `r>=1` is tiny — the recurring cost is elsewhere.

## Decisions / findings

1. **All sends/receives are `nonblock=False` (BLOCKING)** — `appliance_session.py:75,79`. The "nonblock parallel bands" comment in `send_kv_band` (`appliance_real.py:228`) describes the *native* `launch.py`, NOT this `ApplianceSession` wrapper. So `band_send`/`x_send`/`recv16` each include the full wafer round-trip, and **`recv16` = 16 serial blocking D2H round-trips** => batch receive (one `receive(16*S)`, `VERB_EXCH`) is the biggest known lever (see [specdec-d2h-latency](specdec-d2h-latency.md)).
2. **Double conversion on every send** — `appliance_real.py:229` builds a Python list `list(int(x) for x in band_u32)`, then `appliance_session.py:74` does `np.asarray(...).copy()` straight back to uint32. `band_u32` is already a uint32 numpy array, so the `list(int(x))` per-element loop is pure waste (the `input_array_to_u32` slow path). Cheap, obvious fix regardless of the timers.

## Instrumentation (uncommitted on `lexu/specdec-real-kernels`, gated `IOP_MODEB_TIMING=1`)

- `draft_window` prints per round (worker/pod log): `[MODEB_TIMING r=N] total=.. | band_build=.. band_send=.. | x_build=.. x_send=.. | recv16=..(step0=.. rest=..) | tsc=..`
- `gateway_frontend` prints per round (driver.out): `[MODEB_TIMING driver] r=N ... rtt=..`
- Then `transport = driver_rtt - worker_total`; the phase split inside `worker_total` says recv-bound vs convert-bound.
- Env reaches the pod via the `/proc`-captured worker env (`controller.py:260`).

Expected on `r>=1`: tiny `band_send`/`x_send`; the mass in `recv16` (=> batch receive) or in `driver_rtt - worker_total` (=> transport).

## MEASURED on device (2026-07-07) — the culprit is `repack_continuation_band`, NOT the ring

4-config A/B on real WSE-3 (`IOP_MODEB_TIMING`/`_BATCH_RECV`/`_NONBLOCK_SEND`). **The recurring round = a STABLE ~34 ms worker part + a HIGHLY VARIABLE transport part.** Do NOT trust a single "~38 ms" figure — that came from 2 bring-ups that both happened to hit LOW transport (~4 ms). An independent hand-run hit ~115 ms recurring (transport ~81 ms). So 38 ms and 115 ms are BOTH real; they differ in transport, not the worker.
- worker/ring ~34 ms = `band_build` 19 ms (host CPU) + `recv16` ~14 ms (fabric). Stable across runs.
- transport = `driver_rtt − worker_total` = the `launcher.run` gRPC hop through the flaky L7 :443 ingress. Swings ~4 ms (good ingress) to ~80 ms+ (bad). THIS is the dominant, variable cost — earlier dismissed as "~4 ms" was a low-transport-regime artifact.
- Sampling lesson: 3 rounds within ONE bring-up are correlated (same transport regime), NOT independent samples. Characterizing transport needs multiple INDEPENDENT bring-ups.
- The old 115 ms DEADLINE round also had the `list(int(x))` double-conversion (~26 ms/pod, since removed), but that is a side issue — the transport swing is the real story. Worker breakdown (`csctl log-export <jid> -p <path>` then unzip; the pod stdout carries the `[MODEB_TIMING r=N ...]` lines):

```
baseline r=1 perstep nb=0: total=34.3 | band_build=19.3 band_send=0.8 | recv16=13.9(step0=3.4 rest=10.5) | tsc=0.2
both     r=1 batch  nb=1 : total=33.8 | band_build=19.1 band_send=0.4 | recv16=14.1               | tsc=0.0
```

Recurring round = **band_build 19 ms (host numpy) + recv16 ~14 ms (FABRIC: 16 tok x ~0.7 ms) + transport ~4 ms (rtt-worker) + ~1 ms**. Findings:

- **`repack_continuation_band` = 19 ms is the dominant cost** — a pure-numpy `P*Pw` (~12k tiles) Python loop building the meta band. **Fixed: vectorised (where(arange(P)<r,q+1,q) + broadcast), byte-identical (verified across P/Pw/A), ~145x faster local, 19 ms -> <1 ms.** kv_transform.py:394. Offline-testable (test_kv_transform).
- **Ring levers were the wrong target.** batch receive: recv16 14.1 vs 13.9 = NO help (recv16 is fabric, the receive waits on compute regardless). nonblock send: band_send 0.4 vs 0.8 = 0.4 ms (band_send already tiny). Both kept opt-in but marginal. nonblock DID help round-0's full-KV send (14->5.2 ms), one-time only.
- **Transport (`launcher.run`) is only ~4 ms/round** — not the bottleneck. (Round-0 is different: driver rtt ~8 s vs worker 77 ms -> ~7.8 s in the first exchange's transport/KV path; one-time, not investigated.)
- recv16 ~14 ms = kernel compute (~0.7 ms/tok ~ 1400 tok/s); irreducible on our side -> kernel work.

Net: repack fix alone ~halves the recurring round (38 -> ~19 ms). Below that needs kernel (recv16) or multi-round transport batching. Lesson: MEASURE — the 3 hypothesised levers (batch/nonblock/kernel-merge) all missed the real 19 ms host-numpy cost. Fix is UNCOMMITTED on `lexu/specdec-real-kernels` pending a device re-run to confirm band_build drops.

## MEASURED 2026-07-08 — 41-round within-session distribution + the repack fix + KV-transfer is host-bound

**The "repack fix"** = vectorising `repack_continuation_band` (kv_transform.py). The OLD code built the P*Pw (~131k tiles for greedy_kv P=256/Pw=512) meta re-arm band with a Python double-loop (`np.array([iter,A])` per tile) = ~19 ms/round on the pod. Vectorised to `where(arange(P)<r,q+1,q)` + broadcast = <1 ms, byte-identical (verified across P/Pw/A). This is the per-round "continuation-pack" leg (`band_build`).

**41-round run (NUM_ROUNDS=42, MAX_SEQ_LEN=1024 unchanged, accept-1, repack fix in), ONE bring-up:** every leg STABLE (std < 0.3 ms). Per-round distribution:
- round (driver rtt): p50=18.3 p99=19.9 std=0.27 ms
- worker (appliance): p50=15.1 std=0.06 ; **recv16 (FABRIC) p50=14.0 std=0.05 = 76% of the round** (step0=3.5 first-token + rest=10.5 = 15 tok x ~0.7 ms ~ 1400 tok/s)
- **band_build (continuation-pack): p50=0.1 ms (was 19 ms) — repack fix confirmed at scale**
- transport (intra-cluster): p50=3.2 p99=4.7 std=0.25 ms — STABLE *this session*
- band_send 0.6 / tsc 0.2 — negligible
=> recurring round ~38 ms -> **~18 ms** after the repack fix; remaining big leg is FABRIC (recv16, kernel-side). Transport is stable WITHIN a session (~3 ms); the 115 ms seen earlier was a BAD-INGRESS session (transport is the BETWEEN-session variable). Data+plot preserved at `nc_service/_runs/prof42_saved/` (prof42_raw.txt, parse42.py, modeb_latency_distribution.png).

**KV-TRANSFER overhead is HOST-TRANSFORM-bound, NOT wire.** Inter-node ~10 GB/s => 29 MB KV = ~3 ms wire (134 MB framed handoff ~13 ms). But `repack_kv_band` (decode-side full-KV band builder in `load_kv`, kv_transform.py:367) is the SAME Python-loop class as the continuation band but over the full KV: P*mlpb*2*Pw ~1M tiny-numpy-slice iterations/band x P_Y=4 bands = **3.4 s on gala2 -> ~tens of seconds on the pod CPU (~12x)**. So the KV transfer is dominated by host repack, ~3-4 orders of magnitude over the wire. FIX: vectorise `repack_kv_band` (same as the continuation fix) -> should drop to <1 s. Round-0 decode exchange = 8 s (worker 74 ms, ~7.9 s transport/one-time) and prefill exchange = 17 s are separate one-time costs not yet split. To get the exact wire/transform/other split, instrument `load_kv` + the kv_channel handoff on-device.

## Round timelines (image + artifact)

Image: `../artifacts/2026-07-08-specdec-round-timelines.png` (matplotlib, faithful to device numbers). HTML artifact: `../artifacts/2026-07-08-specdec-round-timelines.html` → https://claude.ai/code/artifact/fd34d5a2-5c48-441b-8056-7efb9464ec28
- Timeline 1 (one-time bring-up ~3.82s): egress 1547 / transform 352 / encode 167 / frame 18 / wire 82 / load_kv 903 / full-KV H2D+1st window 637.
- Timeline 2 (rewind round ~18.1ms): fabric decode 14 / gateway rtt 3.2 / band+seed send 0.6 / tsc 0.2 / band build 0.1.

## Progress slide (artifact)

`../artifacts/2026-07-08-specdec-progress-slide.html` (two slides: rewind-round per-stage breakdown + distribution; KV-transfer status). Also published: https://claude.ai/code/artifact/7b850536-90b5-48f0-a202-d24a75aacb98

## KV-transfer on-device measurement — RESOLVED (2026-07-08, device n=1, rc=0)

**The mode-B PD "failure" was NOT infra.** Earlier I called it a "cluster ingress outage" — a wrong, unfalsifiable "infra" conclusion (cerebras-debugging L3/L9). Corrected by a clean device run (`safe_kvt2`, 90-min cap, job-id cleanup, 4 rounds rc=0): (1) `Could not find coordinator / Empty ingress -> :443` is a BENIGN preamble — it printed in THIS successful run. (2) SdkLauncher buffers stdout until exit, so a prefill pod bringing up (cache-hit compile + fp16 weight H2D + init) is indistinguishable from a hang: frozen driver.out, zero worker-log bytes. (3) prefill bridge comes up **~16 min** after the prefill pod appears; my prior device attempts cancelled at ~10-15 min, i.e. my OWN premature deadline fired just before connect. Decode pod by contrast bound its KV receiver in ~60 s (cache hit).

**Measured KV-transfer split** (blob=134,742,788 B ~128.5 MB, saved `_runs/kvt_saved/kv_timing_2026-07-08.txt`):
- prefill: egress(D2H off wafer)=1546.6ms, **transform=15333.9ms**, encode=169.9ms, frame=18.1ms
- wire (pod->pod TCP, 16 streams): send=**81.7ms** (128MB; the 10-12GB/s leg — negligible)
- decode: unframe=788.7ms, handoff=78.6ms, repack=33.5ms (the vectorized `repack_kv_band` — fast)
- r=0(prefill) rtt=17178ms; r=1 1506ms; r=2 19.0ms; r=3 18.4ms

**Bottleneck = the prefill-side `kv_transform.transform()` at 15.3 s, NOT the wire (82ms).** Root cause: `transform()` (kv_transform.py:320) was a 7-deep Python for-loop (gy,gx,l,c,kv_col,b,s) scattering element-by-element over the full KV. L7 lesson: instrument first — I'd optimized the 33ms repack while the 15.3s transform sat un-instrumented.

**FIXED + DEVICE-CONFIRMED 2026-07-08.** Vectorized `transform()` (numpy index math + one scatter per decode-batch); kept the loop as `_transform_ref` oracle + a byte-equality test (`test_transform_vectorized_matches_ref`), 25 SDK-free realkv tests pass. Second device run (same safe_kvt2 path, remote md5==local so the pod ran the exact code): **transform 15333.9ms -> 351.9ms (~44x on the pod)**, egress/wire/decode unchanged; **r=0 round 17178ms -> 2196ms**, full 4-round run 18721ms -> 3768ms (qps 0.2->1.1), rc=0, pods clean. r=0 is now EGRESS-bound (egress 1.55s). NEXT lever if needed = prefill egress D2H (1.55s) — but the KV-transfer host bottleneck is resolved. NOTE the vectorized transform is UNCOMMITTED on lexu/specdec-real-kernels (working tree), awaiting user's commit call. **42-round device re-run (rc=0, transform fix in place): transform=336ms, r0=2209ms, r1(ingest)=1540ms; REWIND distribution n=41 mean=18.17ms std=0.163 min17.9 max18.8 — stable, tighter than pre-fix 41-round (18.3/0.27). Full 43-round run 4494ms qps=9.6. No pod leak.**

## ~1s serde vs RDMA (2026-07-08) — RDMA won't fix it

The one-time bring-up spends ~1s in HOST serde: encode 167 + frame 18 + decode unframe 790 ~= 975ms. The 790ms unframe = `np.asarray(flat_u32)` on a Python LIST of ~33M ints (`_unframe_blob` pd_real_adapters.py:163) — framework hands decode a list; rebuilding the numpy array is the cost. Array<->list<->array round-trip forced by the opaque-payload contract. **RDMA does NOT alleviate this** — RDMA replaces the WIRE (82ms; warm RDMA collapsed a prior leg 45->5ms), the serde is host CPU on both ends regardless. Serde fix = zero-copy seam (keep KV as ndarray/bytes, kill .tolist()/np.asarray), same spirit as the transform fix.
RDMA adoption on the real path is ALREADY wired: kv_channel backend seam (`IOP_KV_BACKEND=tcp|rdma`, _resolve_backend reads env), rdma_backend.py + rdmaw_ctypes.py in-tree, KvSender/KvReceiver in appliance_handlers default to the env (no hardcode), and appliance_handlers.py:264 pre-builds librdmaw.so at __IOP_INIT__ when rdma. The ONLY thing pinning tcp was run_e2e_pd_modeb_real.sh:36 `export IOP_KV_BACKEND=tcp` — changed to `${IOP_KV_BACKEND:-tcp}` (uncommitted). kv_bw_check.py (in main) is the standalone TCP-vs-RDMA wire tool. ContextBase log: cKDd6Y66yG under PD Disaggregation living doc.

**DEVICE RDMA VALIDATION 2026-07-08 — RDMA did NOT engage; the env flip is NOT sufficient (my "just flip IOP_KV_BACKEND" claim REFUTED, cerebras-debugging L8).** Ran `IOP_KV_BACKEND=rdma` on the real path (rc=0, 15 rounds). Verified three ways the run used TCP not RDMA: (1) the wire print `[KV_TIMING wire] ... streams=16 (cold; excl handshake if warm)` is emitted ONLY by `_TcpTransport.send` (kv_channel.py:280); (2) `KvSender.send` took the `elif _backend_name=="tcp"` branch (kv_channel.py:422) => resolved tcp; (3) zero RDMA evidence in pod log-export (no librdmaw pre-build from appliance_handlers.py:264, no RdmaTransport). So the prefill pod's KvSender saw IOP_KV_BACKEND != rdma. Likely cause: controller.py:302 forwards IOP_* to the worker but with `and _key not in env` (won't overwrite a pre-existing value), or the var didn't reach the prefill pod; SDK didn't dump pod env so exact value unconfirmed. Wire numbers therefore are TCP: 82ms (run1) / 69ms (this run) = run-to-run variance, NOT an RDMA measurement. To actually engage RDMA: pass backend explicitly at the appliance_handlers KvSender/KvReceiver construction (don't rely on env-forwarding + default), or fix the controller forwarding guard, + add a resolved-backend diagnostic print. BUT per the serde analysis RDMA only touches the ~70-82ms wire, not the ~1s host serde — so this is a MINOR lever; the real win is the zero-copy serde fix.

**ROOT CAUSE — NOT a regression from our branch; a pre-existing merged-PR gap (verified via git diff main...HEAD 2026-07-08).** (1) Our branch touched NONE of the RDMA path: controller.py (IOP_* forwarding), rdma_backend.py, rdmaw_ctypes.py = 0 diff vs main; appliance_handlers = only the additive IOP_REAL_KERNELS/mode-B seam (the `IOP_KV_BACKEND==rdma` librdmaw pre-build block is MAIN's, untouched); kv_channel = only my +4 KV_TIMING print. (2) main's `build_prefill_handlers` creates `KvSender(peer)` and `KvReceiver(bind=...)` with NO explicit backend (env-reliant) — that is MAIN's design. (3) main's `run_e2e_pd.sh` header states TCP is "the only path validated so far"; RDMA "requires librdmaw.so + an RoCE HCA; see the CS-3 device gate". (4) main's RDMA tests are transport-level loopback, `@skipif(not _HCA_READY)` (need librdmaw.so + RDMAW_TEST_DEVICE), and the off-HCA tests assert `backend=rdma` RAISES RdmaUnavailable (fail-loud, never silent TCP fallback). => The full-PD RDMA path (driver -> appliance_handlers env -> KvSender resolve) was NEVER validated end-to-end in the merged PR; my device run is effectively the first attempt and it resolved tcp. Since off-HCA rdma is designed to RAISE and the run instead SUCCEEDED on tcp, the env simply never resolved to rdma at the pod's KvSender. RDMA transport itself was validated standalone earlier (warm 45->5ms, [[warm-async-kv-path-validated]]) — the gap is purely the PD-integration env->backend wiring.

**FIXED + RE-VALIDATED 2026-07-08 (commit e8f8feb on lexu/specdec-real-kernels).** Root cause CONFIRMED = controller.py:260/302: worker env seeded from the original /proc env, then IOP_* forwarded only `if _key not in env` — a stale worker-env IOP_KV_BACKEND shadowed the run's rdma choice. Fix: controller env is authoritative — overwrite every IOP_* except IOP_SRC/IOP_CONFIG/IOP_BUILD_HANDLERS. Also appliance_handlers now passes IOP_KV_BACKEND explicitly to KvSender/KvReceiver + prints `[KV_BACKEND] ... resolved=<name>` (so a silent tcp fallback can never again be mistaken for an rdma measurement). 27 SDK-free tests pass. Device re-run: **RDMA NOW ENGAGES** (no more tcp fallback) — proven by the pod raising `rdmaw_ctypes.RdmaError: rdmaw_open: device rxe0 not found` -> `RdmaUnavailable` at decode `KvReceiver(backend=rdma)` bind. **So RDMA is UNUSABLE on the current CS-3 PD pods: no RoCE device (rxe0 soft-RoCE not configured / no HCA exposed to the pod).** It fails LOUD (PR's intended off-HCA behavior), rendezvous aborts before prefill comes up (only the decode jid appears; no leak). To enable RDMA pod-to-pod: configure soft-RoCE rxe0 on the pods OR point rdma_backend at a real HCA device/gid present on the pod (infra/config, not our code).

**RDMA NOW WORKS ON DEVICE (2026-07-09, commit dc60b4e) — and it does NOT help.** Root cause of the earlier rxe0 failure = OUR wrong defaults, not missing hardware. Per the h2d-explore doc [[h2d-host-device-bandwidth]] + the rdma-explore example (happyandslow/WaferEngine@lexu/h2d-explore): the pods HAVE real RoCE HCAs mlx5_0/mlx5_1 (ConnectX-5, verbs 0666); rxe0 is only a soft-RoCE dev fallback; and GID idx 0/1 is link-local IPv6 (RoCE v1) that does NOT route pod-to-pod — you need the RoCE v2 IPv4 GID. Fix: ported dump_gid_table/auto_gid_idx (pure /sys parse) into rdma_backend, defaulted IOP_RDMA_GID_IDX=auto, run with IOP_RDMA_DEVICE=mlx5_0. Device re-run (jids btcpry+nbrv78, rc=0, 15 rounds): both ends log `[KV_BACKEND] resolved=rdma`, 128MB KV crossed pod-to-pod over RDMA. **BUT r=0 handoff = 2283ms (rdma) ~= 2196ms (tcp) — statistically identical**, because the wire is ~70-82ms of a ~2.2s handoff dominated by prefill egress (1.54s) + transform (0.34s) + decode unframe (0.79s). So RDMA changed the transport and r0 did not budge — EMPIRICAL PROOF the wire is not the lever. NOTE rdma_backend emits no `[KV_TIMING wire]` line (the "69.4ms streams=16" seen in kvt_rdma was STALE TCP data from a prior run; clean kvt_rdma/ between runs). **CONCLUSION: the ~1s host serde (unframe 790ms = np.asarray on a 33M-int python list; zero-copy np.frombuffer/registered-buffer fix) is the real, transport-independent target. RDMA is done — works, doesn't help.** The "warm 45->5ms validated" note is contradicted by the h2d curation (RDMA never benchmarked on EPCC = expectation, not measurement) — treat as mislabeled.

## Measurement boundaries (what the timers actually mean) — 2026-07-08

All KV_TIMING/MODEB_TIMING numbers are HOST `time.perf_counter` brackets (no wafer TSC in these), so no cross-clock skew IN a number, but they measure host wall-time of blocking ops, NOT on-wire bytes. Specifically: **`egress` is NOT isolated D2H** — it brackets `PrefillApplianceReal.prefill()` (appliance_real.py:370) = send prompt H2D -> BLOCK on the wafer prefill FORWARD COMPUTE -> recv logits -> recv 128MB KV D2H -> host reassemble. So `egress`~=prefill RUN+READBACK (compute+transfer lumped), can't split. I mislabeled it "(D2H)"; corrected. `rtt` (gateway_frontend.py:116) is a DRIVER-node clock; the prefill KV_TIMING sum is a PREFILL-POD clock; "rtt ~= sum" is a cross-machine plausibility check (gap ~= driver<->pod hop), NOT an identity. Isolating true D2H needs on-wafer TSC-at-emit vs host-recv ([[toy-emit-recv-d2h-modes]]).
Round flow (modeb_adapter.draft_window): round 0 (rearm_A=None) sends the FULL 128MB KV bands H2D (self._full_bands from load_kv's repack_kv_band); round r>0 sends the tiny continuation band (repack_continuation_band). So driver r=1 (first decode) = load_kv(unframe 790+handoff 79+repack 34=903) + full-KV H2D + first fabric window; r>=2 = tiny band + fabric window (~18ms).

## Rounds / NUM_ROUNDS mechanics + standing rule (>=10 rewind rounds)

`IOP_REAL_ROUNDS` (= the `run_e2e_pd_modeb_real.sh N` arg) becomes the decode kernel's compile-time `NUM_ROUNDS` (`pd_real_adapters.py:352`, OVERRIDES the config's baked value). It sizes the decode ports (`MAX_OUTPUT_LEN = max_output_len_worst * NUM_ROUNDS`, i16 => NUM_ROUNDS <= 42 at MAX_SEQ_LEN=1024). So each distinct rounds value is its OWN decode compile — but the decode compile is the CHEAP one (~60s-few min); the ~16-min bring-up is the PREFILL kernel, which has NO NUM_ROUNDS and is reused for any rounds count. => running more rounds costs ~the same bring-up.
Round map for `run_e2e ... N`: driver runs N+1 rounds = r0 prefill (prefill pod) + r1 KV-ingest (decode load_kv, ~903ms) + r2..rN = **N-1 pure steady-state rewind rounds** (~18ms each). So for >=10 pure rewind rounds use N>=12; N=42 gives 40 (matches the old 41-round distribution). `IOP_MOCK_ACCEPTED=1` (accept 1 tok/round) keeps the accepted position in bounds over many rounds (256+N << 1024). **STANDING RULE (user 2026-07-08): always drive >=10 rewind rounds on mode-B device runs — 3-4 rounds cannot characterize the distribution.** run_kvt2.sh (scratchpad) set to ROUNDS=42.

## Commands / paths

Also posted on PR #10: https://github.com/lausannel/nc_service/pull/10#issuecomment-4906340575
Code: `waferengine/samples/specdec/realkv/modeb_adapter.py`, `appliance_real.py`; `waferengine/engine/io_pipeline/executor/appliance_session.py`; `.../gateway/gateway_frontend.py`.

## Last updated

2026-07-07
