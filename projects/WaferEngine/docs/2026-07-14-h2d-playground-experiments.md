# h2d-playground — Host↔Device & Cross-Pod Transport Bandwidth/Latency Exploration

**Source:** `happyandslow/WaferEngine` branch `lexu/h2d-explore`, dir `h2d-playground/`
**Compiled:** 2026-07-14 (summary of ~25 experiment studies)
**Scope:** How fast can bytes move host↔WSE-3, pod↔pod, and controller↔worker on the EPCC CS-3 cluster — the transport substrate for streaming/disaggregated Llama-3 decode.

---

## TL;DR — the load-bearing conclusions

1. **memcpy host-wall bandwidth is a lie.** `memcpy_h2d` returns on queue-submission, not wire completion, so host-wall reports up to ~27 GB/s while on-device TSC shows the true per-PE drain rate is **~3 GB/s** on small grids (e1, bandwidth-test). Always measure with on-device TSC, and only trust steady-state (high loop count, rep-0 dropped).
2. **A single SdkLayout direct-link stream tops out at ~1.08 GB/s** (e3.6, confirmed by e3/e3.5). Scaling streams helps only sub-linearly and only if `io_loc` is **explicitly pinned**: 16 pinned streams reach ~11–15 GB/s aggregate; auto-placed streams cap at ~4 GB/s regardless of payload (bandwidth-test-parallel, e3.7). Pinning is *the* knob.
3. **Big grid unlocks H2D memcpy BW**: 512×512 PEs → 9.2 GB/s H2D (but D2H collapses to 1.88 GB/s on that grid); 64×16 plateaus at ~4–5 GB/s (bandwidth-test). memcpy `--channels` inflate wall BW but not the drain rate.
4. **Cross-pod host-fabric TCP works and is not the bottleneck**: single flow is per-flow-capped at ~0.63 GB/s; 16 parallel flows hit ~8.7 GB/s aggregate (~2.4× the H2D ceiling) — but only over the fast **10.27.x underlay NIC**; the default 100.64.x k8s overlay caps ~110 MB/s/conn (e5, e13).
5. **For the N-stage decode pipeline, lockstep (one frame in flight) is the dominant latency knob** — collapses canonical N=3 RTT from 58.8 ms to 25.5 ms; direct-ack alone *regresses*, multi-flow gives nothing at small payloads (e7, e8). At Llama-3 hidden-state size (8 KiB/token) per-frame RTT is **0.977 ms** (~0.33 ms/stage) → extrapolated ~10–15 ms/token decode.
6. **SdkLayout direct streams beat the memcpy framework in the pipeline at every practical payload** (1.3×–31×), the win dominated by ~0.6–0.8 ms fixed overhead vs memcpy's linear per-iter wire cost (e10). At **matched wire bytes**, once the stream-count S is tuned per regime, sdklayout *ties* memcpy — the real cost is **framework-call cardinality, not wire bandwidth** (e11 supercolumn).
7. **The controller↔worker link is asymmetric**: a fast one-way UDP door *into* the worker (sub-ms, underlay only), no direct path *out*. Fastest *supported* round trip = a single `launcher.run("printf …")` at **~2.4 ms p50** (bare gRPC floor). Streaming-output polling floor is ~3.5 ms p50 batched / ~2.0 ms p50 single-token FIFO (e9, e16).
8. **RDMA's win is size-dependent and latency-shaped**: ~8× TCP at 4 KB, converging to parity at ≥16 MB where both saturate the ~12.3 GB/s fabric line rate. Durable win is per-op latency (~7.8 µs vs ~65 µs) and near-zero receive CPU with rdma-event (rdma-explore).
9. **Controller-direct 2 GiB → device is stage-bound, not wire-bound**: the device `memcpy_h2d` is 0.2 s (10.6 GB/s); the costs are one-time `SdkRuntime` init (~58 s for a 524k-PE artifact, amortized by a warm server) and recurring `launcher.stage` (~20–30 s at ~90–110 MB/s, does **not** parallelize) (e12).

---

## Master bandwidth summary (single-node host↔device)

| Experiment | Transport / config | Metric | H2D | D2H |
|---|---|---|---|---|
| bandwidth-test | memcpy ch16, 64×16, k4096, loop500 | on-device TSC steady | 5.18 GB/s | 4.77 GB/s |
| bandwidth-test | memcpy ch16, **512×512**, k2048, loop5 | wall | **9.20 GB/s** | 1.88 GB/s |
| bandwidth-test-parallel | SdkLayout direct, S16 **pinned**, K512 | TSC envelope | 12.73 | **15.38** |
| bandwidth-test-parallel | SdkLayout direct, S16 **nopin** | TSC envelope | ~4.4 | ~4.4 |
| e1-memcpy-bulk | memcpy, w64, 16 KiB/PE | host-wall (overstated) | **27.3** | — |
| e1-memcpy-bulk | memcpy | on-device TSC (true drain) | **~3.0** | — |
| e3-sdklayout-bulk-s1 | SdkLayout direct, 1 stream demux | wall slope fit | ~1.7 | — |
| e3.6-direct-multibatch | SdkLayout direct, **1×1 PE**, TSC | on-device (v1 & v2) | **1.08** | — |
| e3.7-parallel-streams | SdkLayout direct, S16 mode-B, TSC | envelope (plateau) | **3.88** | — |
| e14-clean-sdklayout | memcpy COL_MAJOR, NOWSE, cached | host-wall envelope ceiling | **12.13** | (roundtrip) |

Timing-method rule discovered repeatedly: **on-device TSC = wire truth; host-wall = framework/queue/lifecycle overhead**. They diverge by 1.5–3× (and wildly for tiny payloads). `memcpy_h2d` and concurrent-`nonblock` `send` both make host-wall meaningless.

## Master latency summary (cross-pod pipeline & controller paths)

| Experiment | Path | Best result |
|---|---|---|
| e5-direct-link-hack | pod↔pod host-fabric TCP | 0.634 GB/s/flow; **8.71 GB/s** aggregate at N=16; 8 MiB KV block 0.97 ms |
| e6-pipeline-cluster | N-stage device pipeline | verified arithmetic to **N=4**; per-edge single-flow ~80 MB/s |
| e7-timing-decomp | per-iter decomposition (N=3, 1 MiB) | compute 1 µs, host↔device 2.4 ms, **host↔host TCP ~6 ms dominates**; RTT 58.8 ms |
| e8-pipeline-min-latency | +lockstep | N=3 RTT **25.5 ms**; T=8 (8 KiB) **0.977 ms** (~0.33 ms/stage) |
| e10-sdklayout-1PE-vs-memcpy | transport swap | sdklayout **31×** faster at T=1024, 1.3× at T=8; min cluster RTT 0.52 ms |
| e11-sdklayout-fanout | matched wire bytes, supercolumn | S=1 ties memcpy at T=8 (**0.96 ms** ≈ 1040 tok/s); S=4 ties at T=1024 |
| e9-launcher-polling | streaming-output poll floor | batched **3.5 ms p50** (3k+ tok/s); FIFO **2.0 ms p50** single-token (172 tok/s) |
| e12-controller-to-device | 2 GiB → 524k PEs | 79.85 s cold (58 s init + 19 s stage + **0.2 s memcpy**); 24 s warm (stage-bound) |
| e16-controller-worker-direct | controller↔worker | `printf` RPC **2.4 ms p50**; UDP-in underlay sub-ms, 2% loss; asymmetric |
| rdma-explore | RoCE pod↔pod | **12.3 GB/s** line rate; ~8× TCP at 4 KB; latency 7.8 µs vs 65 µs |

---

# Part 1 — Single-node H2D/D2H bandwidth micro-benchmarks

Theme: raw host↔WSE-3 wire bandwidth, memcpy framework vs SdkLayout direct-link, TSC vs host-wall, io_loc pinning, stream scaling.

### bringup/memcpy-min & bringup/sdklayout-min
Smallest working H2D/D2H round-trips (correctness/plumbing bring-up, no BW numbers). memcpy-min: 1 PE, `memcpy_h2d`→`unblock`→`memcpy_d2h`, offline `cslc --memcpy --channels 1`, appliance dispatch via `SdkLauncher`. sdklayout-min: 1-PE echo, `SdkRuntime(memcpy_required=False)`, inline `layout.compile()`, nonblock send/receive with `stop()` as sync. **Footgun documented:** compiling with sim fabric-dims then running on real WSE → `RuntimeError: All ingress tiles must be at the edge of the fabric`; real WSE-3 needs `762,1172`. `--channels` is a memcpy-only knob absent from SdkLayout.

### bandwidth-test (memcpy framework baseline)
Parameterized fork of the SDK example. memcpy `--channels=N`, on-device 48-bit TSC (`f_sync` removes per-PE clock skew, `f_tic`/`f_toc` bracket). Grid m×n PEs, k f32 each; BW = wvlts·4/time · loop_count at 850 MHz.
- 64×16, k4096, ch16, loop500: **H2D 5.18 GB/s, D2H 4.77 GB/s** (steady). Low loop counts give garbage (D2H loop5 reported 54,717 MB/s — warm-up/aggregation artifact).
- 512×512, k2048, ch16, loop5: **H2D 9.20 GB/s, D2H 1.88 GB/s**.
- 32-channel compile **failed**; width-sweep col runs errored (missing dispatch script).
- **Takeaway:** small grids plateau ~4–5 GB/s regardless of channels; big grid pushes H2D to 9.2 GB/s but D2H collapses. Only high-loop steady-state numbers are trustworthy. (SDK cbcore 2.6.0, cluster-server 3.0.3.)

### bandwidth-test-parallel (SdkLayout direct multi-stream)
N single-PE stream pipelines stacked vertically, no demux/mux. v3 TSC sync/tic/toc retrofit; `nonblock=False` toc forces host-side drain so `tscEnd` = wire-complete. Both TSC and host-wall reported; distributed variant spawns N workers each with own `SdkRuntime` + filtered `add_port_mapping`.
- Swept: S=16, B=4096 f32, K∈{32,512,2048,8192,16384,32768}, H2D/D2H, **pin vs nopin io_loc**.
- **D2H pin:** K512 **15.38 GB/s**, K16384 12.54, K32768 11.38. **D2H nopin:** caps ~4.3–4.5.
- **H2D pin:** K512 **12.73**, K16384 11.43. **H2D nopin:** caps ~4.2.
- **Takeaway:** explicit `io_loc` pinning is load-bearing — pinned ~11–15 GB/s, auto ~4 GB/s regardless of payload. SdkLayout direct-link matches the memcpy headline only when pinned. TSC ≫ host-wall.

### e1-memcpy-bulk
memcpy bulk one-shot into W×H grid, each PE `[MAX_LEN]u32`. Dual timing (host-wall + TSC), plus pipelined mode (one tic before a back-to-back loop). `aggregate_warm.py` drops rep 0.
- Swept: ch∈{1,4,16}, grids 8×8/8×16/64×16/256×16, payload 64–4096 u32, row vs col order.
- Host-wall: 8×8 ch1 → 3.66 GB/s max; ch4 → 11.46; 8×16 ch16 → 21.3; width-sweep best **27.3 GB/s** (w64, 16 MiB).
- **On-device TSC plateaus at ~3 GB/s** regardless of grid width or channels (w8 3.13, w64 3.26, w256 3.16).
- row order beats col by ~30–40%; cold rep 0 dominates small transfers (13× at 16 KiB).
- **Takeaway:** host-wall up to 27 GB/s massively overstates truth; real per-PE drain is ~3 GB/s, channel/width-independent. Channels inflate wall (more parallel submission), not the wire.

### e3 / e3.5 / e3.6 / e3.7 — SdkLayout direct-link, single→parallel stream refinement
- **e3-bulk-s1:** single host stream → demux→buffer→mux→d2h, one pass per process. Per-rep BW meaningless (~10 ms lifecycle floor dominates); slope fit across sizes → **~1.7 GB/s** transfer component. Motivated amortization.
- **e3.5-bulk-multisend:** re-arming kernels (demux_adaptor `restart` task) enable N sends per lifecycle. Only a sim smoke result committed; the methodological fix, real numbers landed in e3.6.
- **e3.6-direct-multibatch:** stripped demux/mux to a **1×1 PE**, on-device TSC. v1 (host sends one big array, kernel chunks): saturates **1.08 GB/s** for a single stream. v2 (N host sends, kernel re-arms): same **1.08 GB/s** TSC ceiling, but host-wall throttled by ~12 µs/send fixed cost, converging only at ≥16 KiB/send. TSC is authoritative.
- **e3.7-parallel-streams:** N stacked 1×1 cores, cross-stream TSC envelope aggregate. Mode A serial (blocking) vs Mode B concurrent (nonblock+stop barrier). Default vs **spread** (io_loc pinned to discovered Y positions [0,18,…,1098]).
  - Mode B pl4096: S1 1.08 → S4 3.46 → S16 **3.88 GB/s** (saturates ~S4–8, sublinear, far below 12).
  - Mode B host-wall is worthless (S16 = 141 ms wall → 0.057 GB/s reading); TSC envelope is the only trustworthy metric.
  - **spread variant TSC envelope broke** (~0 for S≥2 — independent per-PE TSC counters on widely-separated cores can't align via naive max-end−min-start); inconclusive, a measurement artifact not a real zero.

### sdk/ (vendored client)
Pinned copy of `cerebras.sdk.client` v2.10.0 (githash 32008fd851). The shared appliance gRPC transport (`SdkCompiler`, `SdkRuntime` memcpy+load/run/stop, `SdkLauncher` compile/run-split, 2 GB gRPC message cap). The SdkLayout stream / io_loc / add_port_mapping primitives live in the installed SDK, not this copy.

---

# Part 2 — Cross-pod / disaggregated pipeline latency

Theme: host-to-host TCP transport between worker pods, N-stage device pipeline, per-component latency decomposition, driving RTT down.

### e4-fake-decoder
Models per-token H2D ingest cost of the llama3-8B 8-block decoder to find the compute knee (KV-ingest-bound → compute-bound). Single-PE kernel cloned from bw_h2d_direct_kernel_v3; v3 TSC timing.
- Step 1: 8 MiB/token → 8.10 ms TSC → **1.04 GB/s on-device, 123 tok/s ceiling** (single stream).
- Step 2: compute is linear at **14 cycles/iter**; knee at **~500k iters** for 8 MiB KV/token.
- Step 3: adding a 2 MiB activation recv on a separate LVDS Y **adds 0 ms** (rendezvous overlaps for free).
- Caveat: 1×1 placement models wire timing, not per-PE store BW (real block is 256×256 PEs). Steps 4–6 TODO.

### e5-direct-link-hack (foundational)
Can two `SdkLauncher`-launched `cs_python` processes talk directly over host-fabric TCP, bypassing the controller? Controller-mediated rendezvous (`rdv.json` via `download_artifact`), then pure host-to-host TCP with length-prefix framing + blake2b verify. Same/cross-host via `boot_id`.
- **A1 sustained single-stream (cross-host, 1 MiB, 10 s):** **0.634 GB/s** (the honest number; v2's 1.5 GB/s was a buffer-drain artifact). ~17% of the ~3.6 GB/s H2D ceiling.
- **A2 chunk sweep:** flat 0.60–0.66 GB/s across 64 KiB–16 MiB → per-flow rate-limited (TCP cwnd / pod QoS), not syscall-bound.
- **A3 parallel scaling (1 MiB, 10 s):** N1 0.632 → N2 1.222 → N4 2.537 → N8 4.880 → **N16 8.713** → N32 8.743 GB/s. Two ceilings: **per-flow ~0.63 GB/s** (holds N≤8), **aggregate ~9 GB/s** (saturates N8–16). 8 MiB KV block: N16 → **0.97 ms** vs H2D 2.33 ms (~2.4× faster).
- **D1:** worker pod = AMD EPYC 9354P, 64 threads, AVX-512, ~67 GiB cgroup, **zero external egress**. **E-block:** `/home` not mounted in SdkLauncher pods; worker→controller TCP firewalled; no shared FS. Deprecated controller-direct `SdkRuntime` works end-to-end at **7.5 ms round-trip** (h2d 3.34 + launch 1.78 + d2h 2.41, 256 B), sustained d2h p50 1.42 ms — flagged as the right streaming-inference architecture; `streaming=True` deferred (hangs).

### e6-pipeline-cluster
Generalizes e5 from 2→N peers in a linear chain. Topology by **sequential reverse-launch** (launch stage N-1 first, pull rdv, bake successor IPs into N-2, …) — after `SdkLauncher.stage(topology.json)` mid-run failed on EPCC (gRPC UNIMPLEMENTED / HTTP 404). Each stage runs an `SdkRuntime` 16×16 memcpy kernel (io[i] += test_data[i]); controller verifies `output == input + Σ make_test_data(k)`.
- Verified arithmetic PASS at **N=2, 3, 4** (N≤4 = EPCC 4-chip ceiling; N=5 pending).
- Per-edge single TCP flow ~80 MB/s (no NODELAY/tuning); per-iter latency grows downstream via back-pressure (N=4: 12/22/38/43 ms). Wall dominated by come-up (sub-100 ms data path). SRAM 12.2/48 KiB per PE.
- Two structural findings: `SdkLauncher.stage()` mid-run push unusable on EPCC (→ reverse-launch, cost N×queue); single-flow-per-edge + back-pressure inflates downstream latency.

### e7-timing-decomp
Decomposes per-iter wall into device compute / device↔host memcpy / host↔host TCP, vs N, K, tile-len T, compute-rounds R. Per-PE on-device TSC brackets the R-round fadd loop; Task-14 ack channel measures E2E RTT on stage 0's clock (pods can't reach NTP).
- Canonical (N=3, K=64, T=1024, R=1): on-device compute **1 µs/iter**; host↔device ~2.4 ms (h2d:d2h ≈ 1:3, ~0.55 GB/s d2h); **host↔host TCP dominates ~6 ms** (~1.58 ms wire + ~4.5 ms back-pressure). RTT **58.8 ms**.
- R axis: device_ms linear 0.001→6.447 (R=1→10000) — TSC validated. `launch(nonblock=False)` returns before kernel done, inflating d2h at high R (artifact).
- N axis: **RTT super-linear 25.0 / 58.8 / 120.3 ms** (naive N×max-stage predicts 18/27.5/49). K axis: steady at K≥32; RTT grows with K (queueing). T axis: 16× payload → ~21× time; per-flow TCP 0.046/0.17/0.49 GB/s (below e5 due to back-pressure).
- **Takeaway:** compute negligible, host↔host TCP + queueing dominate; canonical decode token latency ~30–60 ms → to hit ~20 ms/token, shrink payload/token and/or multi-flow. Motivated e8.

### e8-pipeline-min-latency
Attacks e7's three RTT inflators with host-side knobs (device kernel unchanged): direct-ack channel, **lockstep (`--max-in-flight=1`)**, multi-flow per edge.
- M1 direct-ack only: median 58.7 ms ≈ e7, mean **regresses** to 73 ms (queueing).
- **M2 +lockstep: median 25.5 ms** (47.5 ms saved, 2.31× faster than e7). Stage-0 send collapses 7.2→0.64 ms.
- M3 multi-flow (lockstep): M=1/4/8/16 all ~25.5–25.9 ms — **no benefit** at 1 MiB (thread overhead beats negligible wire).
- M4 N axis (lockstep): **linear** 12.98/25.86/38.68 ms (~12.85 ms/stage) vs e7's super-linear.
- **M5 T axis (lockstep M=1): RTT linear in payload** — `RTT ≈ 0.024·T + 0.79 ms`; best **0.977 ms at T=8 (8 KiB)** (~0.33 ms/stage), fixed floor ~0.5–0.7 ms below 64 KiB.
- **Headline:** lockstep is the single dominant knob (58.8→25.5 ms); direct-ack alone regresses; multi-flow useless at these payloads. At Llama-3 8B hidden-state (8 KiB) per-frame RTT is 0.977 ms → extrapolated 32-layer decode ~10–15 ms/token (~70–95 tok/s): the pipeline-cluster architecture reaches interactive streaming latency.

### e13-host-only-bench
Isolates whether e11's slowness is the wire or non-LVDS overhead by stripping all WSE/SDK/LVDS while keeping e11's exact TCP threading model. A/B against e5's simpler 1-socket-per-stream loop; NIC-probe scripts inventory interfaces.
- e11 mux-queue+barrier+pool caps ~27 MB/s/conn; 100.64.x k8s overlay caps ~110 MB/s/conn.
- `TCP_NODELAY` collapsed throughput (~0.11 GB/s) vs e5 Nagle-on (~9 GB/s) — a Nagle/iov interaction.
- **Post-NIC-fix (48e66eb): ~1.96 GB/s aggregate at S=4** over the fast **10.27.x underlay**, near e5 parity.
- **Takeaway:** the wall was interface/path selection + TCP tuning, not the 62-socket frame shape. Fast underlay NIC is surfaced only via specific interface enumeration.

---

# Part 3 — Transport selection for the pipeline & streaming

### e10-sdklayout-1PE-vs-memcpy
Swap host↔device transport in the e8 pipeline from memcpy framework → SdkLayout direct-link streams. Compute body shared (R=1 fadd); RTT-difference is transport-only. **Not apples-to-apples on wire bytes** — memcpy pushes 256·T·4 B/iter (16×16 grid), sdklayout 1·T·4 B/iter (1 PE); matched on per-PE payload.
- Block A canonical (T=1024, lockstep): sdklayout **0.85 ms** vs memcpy **26.39 ms → 31.2×**.
- Block B (N): sdklayout +0.33 ms/stage vs memcpy +12.98 ms/stage (~40× cheaper marginal).
- Block C headline: memcpy `RTT≈0.0250·T+0.76`; sdklayout flat `≈0.0002·T+0.63` (fixed-cost dominated). Speedup 1.3× (T=2) → 30.8× (T=1024). **T=8: 0.72 vs 0.97 ms → 1.3×** (lockstep), ~5× under no-cap. Min cluster RTT **0.52 ms** (T=64).
- Architectural: SdkLayout port_map/flow-id metadata lives only in the in-process `layout.compile()` object → each stage builds+compiles+runs in one process (~30 s/stage extra).
- Caveat driving e11: matched on per-PE payload, not wire bytes.

### e11-sdklayout-fanout (supercolumn)
Does sdklayout still win at the **same wire bytes** (256·T·4 B/iter)? Two new transports: **x16** (16 parallel LVDS streams over a 16-PE strip) and **x16x16** (full 256-PE grid via a supercolumn topology). S knob = LVDS fan-out (divisor of 16): S=16 → direct LVDS per row; S<16 → a dispatch chain (dispatch_pe demuxes host wavelets, peels its row east, forwards the rest south through gap PEs; compute rows relay via a two-color checkerboard forced by CSL's unidirectional-per-PE color rule).
- x16 T-sweep: latency floor ~5.5–6 ms even at tiny T (T512 skipped — ran out of PE SRAM: 32 KiB recv + 32 KiB test_data > ~44 KiB pool).
- **x16x16 S-sweep (headline):**

  | S | T=8 | T=1024 |
  |---|---|---|
  | 1 | **0.96** | 28.54 |
  | 4 | 1.91 | **26.41** |
  | 16 | 5.57 | 30.17 |
  | memcpy | 0.97 | 26.38 |

  T=8 monotonic in S (~0.6 ms Python/SDK overhead per extra stream = 1 send + 1 recv); T=1024 U-shaped, min at S=4.
- **Headline (SUPERCOLUMN_ANALYSIS):** Phase 2c overturns the "memcpy wins" reading — the load-bearing cost is **framework-call cardinality, not wire bandwidth**. Tuned per regime, sdklayout matches memcpy at both anchors under matched bytes. For streaming at T~8 use **S=1** (0.96 ms/token ≈ 1040 tok/s). The analysis documents exact placement (`_DISPATCH_X=1`, `_ROW_X0=2`, `_Y_STRIDE=18`, 17 gap PEs/hop), proves two colors are the minimum coloring (a color is unidirectional per PE), notes dispatch colors are region-scoped, and flags the steady-state bottleneck (dispatch[0] RAMP handles 128 chunks/iter vs dispatch[R-1]'s 32).

### e14-clean-sdklayout
Clean minimal-overhead multi-stage pipeline benchmark (real WSE compute in the data path), and finding the fastest WSE transport + host-buffer layout. N pods, each an x16x16 supercolumn kernel; each edge is S parallel TCP conns (e5-style, no mux). Two transports: `sdklayout_x16x16` and `memcpy` (canonical). Host-wall envelope + per-iter RTT. Shape: 2 GiB/iter roundtrip, 1024×512 PEs, tile_len 1024, ch16, K=8, S=16.
- **memcpy COL_MAJOR, no-kernel, cached (canonical):** N=1 RTT **0.774 s** (envelope 2.77 GB/s); N=2 **1.748 s**; N=3 **3.040 s**. Adding a stage is **super-linear** (per-stage wall 0.78→0.96→1.13 s from shared RoCE contention); fit `RTT(N) ≈ 0.16·N² + 0.50·N + 0.12 s`.
- **NOWSE cached ceiling:** envelope **12.13 GB/s**, RTT 0.176 s (host+wire ceiling).
- **Sub-batching load-bearing:** `--h2d-sub-batch-wavelets=65536` → multi-GB/s; `=0` (one big send) caps **~80–140 MB/s** (un-sub-batched N=2 = 0.14 GB/s, RTT 16 s).
- **memcpy COL_MAJOR vs ROW_MAJOR:** 2 GiB 519 vs 2540 ms (4.9×), linear (intercept ≈0) → a per-byte host-side transpose, a free ~5× win.
- **Takeaway:** memcpy COL_MAJOR + 65536-wavelet H2D sub-batching is the fast, simple transport; pipeline depth cost is super-linear (shared RoCE contention). Clean rewrite dropped ~70% of e11's LOC with no perf loss — 1-TCP-conn-per-stream is as fast as mux.

### e15-sdklayout-streaming (PLAN ONLY)
Design/handoff brief, not implemented. Proposes replacing e14's memcpy with SdkLayout direct-stream to reach RTT ≤ memcpy on the 2 GiB benchmark, ideally beating it via h2d/d2h overlap and true wavelet-by-wavelet streaming (natural for token-by-token decode). Baseline to beat: e14 memcpy COL_MAJOR (N=1/2/3 = 0.774/1.748/3.040 s). Cites expected sdklayout headroom 11–12 GB/s at S=16 pinned. Documents 7 known traps (io_loc auto-pick ~4 GB/s cap; one-big-send ~80–140 MB/s cap; blocking-drains-own-stream serialization; `compile(cmaddr=None)` failure; TSC plateau; SDK 1.13.2 pybind quirks; suspected host-buffer-order transpose). Open decisive risks: whether low early sdklayout numbers were io_loc/sub-batching or a genuine single-streamer bottleneck, and whether the SDK actually overlaps h2d/d2h.

---

# Part 4 — Controller/worker paths, RDMA, and KV corpus

### e9-launcher-polling
Migrate streaming output off deprecated `memcpy_d2h` onto supported `SdkLauncher.run()` polling; characterize the per-token observability floor at 3k–30k tok/s. Worker daemon emits `<emit_ns>,<seq>` to a file/FIFO; host drains via `launcher.run("dd …")` gRPC round-trips. Latency = recv_ns − emit_ns − δ (calibrated clock offset).
- **B1 producer rate {500–30k Hz}:** RTT p50/p99 flat ~3.6/4.2 ms; batches grow 2→118 tok/poll; **zero loss**. p99 latency 5.9→21.2 ms at 30 kHz (scheduler jitter).
- **B2 poll cadence:** L ≈ S + P/2; gap=0 p50 3.55/p99 5.60 ms (283 polls/s); gap=50 backlog hits 4 KB cap → 202 ms p50.
- **B3 chunk size:** <1 KB saturates (256 B surfaces only 28% of tokens); ≥1 KB daemon-bound.
- **B4 FIFO (key):** exactly **1 token/poll at p50 2.00/p99 2.30 ms** (~RTT/2), but throughput collapses to **172 tok/s** (unconsumed tokens dropped silently).
- **B5 stability:** 10 min, RTT p50 ~3.6 ms flat, **zero seq gaps across 1.8M tokens**.
- **Takeaway:** the granularity floor depends on the backing store, not the RPC. Batched-file = RTT-limited ~3.5 ms p50, 3k+ tok/s. FIFO = ~2 ms p50 single-token, <200 tok/s (interactive chat). memcpy_d2h (1.42 ms) marginally faster but deprecated; B4 is the closest supported path.

### e12-controller-to-device
Controller-node wall time to land 2 GiB onto 512×1024 = 524,288 PEs, per-hop breakdown, 3 strategies. 4 KiB/PE, 1 warmup + 3 timed, median.
- **V1 cold:** **79.85 s** (0.027 GB/s) = `launcher.stage` ×4 chunks **19.4 s** (2 GB gRPC cap forces split) + dispatch 1.39 + worker read 0.61 + **`SdkRuntime.load()+run()` 58.3 s (73%)** + **`memcpy_h2d` 0.20 s (10.6 GB/s)**.
- **V2a warm (seq):** 24.3 s (stage-bound). **V2b warm (par M=4):** 29.7 s — **no speedup** (gRPC stub serializes stream_unary uploads).
- **V3 (controller-direct SdkRuntime):** BLOCKED — `sdk_runtime_create` HTTP 502 from ingress (regression, worked 2026-05-07).
- **Takeaway:** device memcpy negligible; the two real costs differ in lifetime — `SdkRuntime` init ~58 s is one-time (amortized by warm server); `launcher.stage` ~20–30 s at ~90–110 MB/s is recurring per-transfer and does **not** parallelize. Warm decode server: ~20–30 s to ingest each 2 GiB of weights/KV, stage-bound.

### e16-controller-worker-direct
Is there any direct (non-gRPC) controller↔worker path faster than e9's polling floor (target ≤1 ms)? Live wsjob probes A2–A5; arrival proven out-of-band (worker logs source+payload, read back over gRPC).
- **Connectivity:** TCP FAIL both NICs; UDP forward — underlay 10.27.x delivers (a C→W datagram arrived, SNAT'd to 10.24.2.176), overlay 100.64.x 100% lost. Return path blocked → forward-open/return-blocked **asymmetry**.
- **A2 one-way UDP:** underlay 196/200 (**2% loss**), one-way p50 sub-ms (δ-calibrated L ∈ [0,~0.9] ms); overlay 100% lost.
- **A3 round-trip:** HYBRID (UDP-in + gRPC-out) vs all-gRPC — 64 B 4.95 vs 9.94 ms; 65 KB **5.96 vs 17.40 ms (2.9×)**.
- **A4 floor:** bare `launcher.run("true")` **2.44 ms** (hard floor); HYBRID-lite `cat` flat ~3.3 ms vs all-gRPC ~8.6 ms.
- **A5 single-RPC `printf` (winner):** p50 **2.40 ms** at 1 B → 2.56 ms at 1 KB, 0 loss, = the bare `true` floor.
- **Takeaway:** asymmetric link — fast one-way UDP door in (sub-ms, underlay only), no direct path out (worker→controller egress destination-restricted). A synchronous round trip needs one gRPC RPC; fastest supported = single `launcher.run("printf …")` at **~2.4 ms p50**. Sub-2.4 ms unreachable without a cluster-admin egress change. UDP-in only pays for large inputs (2.9× at 65 KB) or async streaming. Deprecated `memcpy_d2h` = 1.42 ms but 502-regressed.

### rdma-explore
On EPCC's 100 GbE Mellanox ConnectX-5 RoCE fabric, RDMA-Write BW/latency vs the TCP envelope; decision gate for porting `pipeline_stage` from TCP to RDMA. Tools stripped (no perftest/UCX/headers) → vendored infiniband headers, hand-rolled C verbs bench (`rdmaw.c` via ctypes) + `ibv_rc_pingpong`. RoCEv2 GID idx 5, mlx5_0, 16 QPs.
- **ibv_rc_pingpong (RDMA vs TCP-echo):** 4 KB 1.05 vs 0.126 GB/s (**8.3×**, 7.8 µs/iter); 64 KB 7.21 vs 1.10 (6.5×); 1 MB 11.14 vs 3.94 (2.8×); 16 MB 11.54 vs 4.65 (2.5×).
- **Custom RDMA-Write bench (poll/event/tcp-16):** 4 KB 0.055/0.057/0.044 (latency-floor, ~74 µs/iter, RDMA≈TCP); 1 MB **13.76/14.25/8.54** (RDMA ~1.7×); ≥16 MB all pinned ~**12.3 GB/s line rate** (converge). rdma-event recv CPU near-zero (0.002 s/GB) vs rdma-poll busy-poll (up to 283 s/GB at 4 KB).
- **Takeaway:** RDMA's win is size-dependent (~8× at 4 KB → parity ≥16 MB where both saturate ~12.3 GB/s) and latency-shaped (7.8 vs 65 µs per op). Split decision: RDMA for latency-bound per-token activations, TCP fine for bulk. (Also validated in the disaggregated-PD work: RDMA works but does not help the KV-handoff bottleneck.)

### orca_kv_pack_mini
Not a BW/latency study — data-prep. Produce/package a corpus of real prefill KV caches from Meta-Llama-3-8B (bf16) over 200 OpenOrca prompts, in a self-describing on-disk format loadable back into a `transformers.DynamicCache`. Format: 8-byte magic `KVCACHE\0`, uint32 version, JSON header (model config: 32 layers, 32 heads, 8 KV heads, hidden 4096, head_dim 128; per-layer k/v offsets/shapes `[batch, num_kv_heads, seq_len, head_dim]`), raw blob. No truncation.
- 200 caches in manifest (bf16). Tokens: mean 218, median 88, min 6, max 2674, p95 698. Per-item ~**131 KB/token** (32 layers × 2 × 8 KV heads × 128 head_dim × 2 B bf16 = 131,072 B/token). Committed tree has 2 blobs + full 200-item manifest.
- **Takeaway:** infrastructure — a versioned KV-cache file format + round-trippable loader + 200-prompt OpenOrca corpus, realistic input for downstream KV-movement experiments. The ~131 KB/token bf16 KV footprint is the load-bearing scale number for those transfers.

---

## Cross-cutting methodology lessons

- **On-device TSC vs host-wall:** the single most repeated lesson. TSC (sync/tic/toc, 850 MHz, ref-clock corrected) is wire truth; host-wall folds in queue-submission/lifecycle/drain overhead and lies by 1.5–3× (worse for tiny payloads / concurrent nonblock sends). Report both, trust TSC. (See `cerebras-sdk-tsc-vs-hostwall-diagnostic` skill.)
- **io_loc pinning** is decisive for multi-stream SdkLayout BW (~4 → ~12 GB/s).
- **Sub-batching H2D** (65536 wavelets) is decisive for memcpy pipeline BW (one-big-send caps ~80–140 MB/s).
- **COL_MAJOR host-buffer order** avoids a per-byte transpose → free ~5×.
- **Lockstep (one frame in flight)** is decisive for pipeline RTT; multi-flow and direct-ack are not (at small payload).
- **Framework-call cardinality**, not wire bandwidth, is the real cost at small per-token payloads (S=1 beats S=16).
- **NIC selection**: 10.27.x underlay (~1.2 GB/s/conn) vs 100.64.x k8s overlay (~110 MB/s/conn) — only surfaced via `psutil.net_if_addrs()` / specific interface enumeration.
- **Cluster gotchas:** `SdkLauncher.stage()` mid-run push unusable on EPCC (→ reverse-launch); 2 GB gRPC message cap; `/home` not mounted, no worker egress, no shared FS; controller-direct `SdkRuntime` is deprecated + intermittently 502-regressed but architecturally the right streaming primitive.
