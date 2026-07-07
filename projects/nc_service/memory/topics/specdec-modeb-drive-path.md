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

## Commands / paths

Also posted on PR #10: https://github.com/lausannel/nc_service/pull/10#issuecomment-4906340575
Code: `waferengine/samples/specdec/realkv/modeb_adapter.py`, `appliance_real.py`; `waferengine/engine/io_pipeline/executor/appliance_session.py`; `.../gateway/gateway_frontend.py`.

## Last updated

2026-07-07
