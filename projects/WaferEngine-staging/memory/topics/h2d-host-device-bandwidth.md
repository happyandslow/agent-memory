---
summary: Findings, techniques and measured numbers from the h2d-playground experiment series (bringup, e1-e16, bandwidth-test, rdma-explore) on host-device and host-host data movement for WSE-3 on the EPCC CS-3 cluster.
tags: [waferengine-staging, bandwidth, h2d, d2h, sdklayout, memcpy, cs3-cluster, measurement, latency, networking]
---

# Host↔Device Bandwidth — the `h2d-playground` series

Source: `happyandslow/WaferEngine`, branch **`lexu/h2d-explore`**, directory
**`h2d-playground/`** (~767 files, 22 experiment dirs). Work done 2026-05-05 →
2026-06-09, mostly on the **EPCC CS-3 (WSE-3)** appliance. Curated 2026-07-08.

This is the *host↔device / host↔host* transport story. It is a **different
topic** from [[prefill-decode-transfer-bandwidth]], which covers the *on-chip*
prefill→decode KV handoff. Related: [[e2e-pdSeparate-device-validation]].

## Summary

The series answers one question in layers: **how fast can bytes get onto and off
the wafer, and what actually limits it?** The headline conclusions:

1. **Auto-picked `io_loc` is the single biggest silent bandwidth bug.** Letting
   the framework place I/O ports for S=16 parallel SdkLayout streams pins
   on-device bandwidth to a hard **~4.2 GB/s plateau regardless of payload
   size**. Pinning `io_loc` explicitly unlocks **8–15 GB/s**.
2. **Most published bandwidth numbers in this repo were measurement artifacts.**
   Short loop counts, host-wall-vs-TSC confusion, and `nonblock` semantics each
   inflate or deflate results by an order of magnitude. See *Measurement traps*.
3. **The two transports have opposite shapes.** memcpy is throughput-oriented
   and **linear in payload**; SdkLayout direct streams are latency-oriented and
   **flat in payload** (dominated by ~0.6–0.8 ms fixed host overhead).
4. **On the CS-3 cluster, the network beats the wafer as the bottleneck.** The
   wrong NIC costs 8×; `order=ROW_MAJOR` costs 5×; missing `--h2d-sub-batch-wavelets`
   costs ~50×. All three are one-line fixes.

## The experiment map

| Dir | Question it answers |
|---|---|
| `bringup/memcpy-min`, `bringup/sdklayout-min` | Smallest working kernel for each transport |
| `bandwidth-test/` | SDK's own memcpy benchmark, `--channels=N` sweep |
| `bandwidth-test-parallel/` | Re-do with SdkLayout direct streams, S parallel streams, `pin` vs `nopin` io_loc |
| `e1-memcpy-bulk` | Bulk memcpy H2D, host-wall vs TSC |
| `e3 / e3.5 / e3.6 / e3.7` | SdkLayout evolution: single-stream → multisend → single-PE batched → parallel streams |
| `e4-fake-decoder` | Decode-shaped traffic stub |
| `e5-direct-link-hack` | **Host↔host TCP between worker pods** (pod-to-pod wire) |
| `e6-pipeline-cluster` | N-stage cluster pipeline, correctness |
| `e7-timing-decomp` | Per-iter latency **decomposition** (compute / h2d-d2h / TCP) |
| `e8-pipeline-min-latency` | Drive per-frame latency down (lockstep, direct-ack, multi-flow) |
| `e9-launcher-polling` | Per-token observability floor via `SdkLauncher.run()` polling |
| `e10-sdklayout-1PE-vs-memcpy` | Head-to-head transport comparison, 49-row sweep |
| `e11-sdklayout-fanout` | 16×16 "supercolumn" fan-out topology (+ `SUPERCOLUMN_ANALYSIS.md`) |
| `e12-controller-to-device` | Controller-node → wafer 2 GiB H2D strategies |
| `e13-host-only-bench` | Pure-TCP bench, no WSE — isolates network from wafer |
| `e14-clean-sdklayout` | **The canonical clean reference implementation** |
| `e15-sdklayout-streaming` | PLAN ONLY — not implemented |
| `e16-controller-worker-direct` | Is there a non-gRPC controller↔worker path? (CONCLUDED) |
| `rdma-explore` | Is RDMA-Write viable on EPCC? (blocked) |
| `orca_kv_pack_mini` | 200 Llama-3-8B prefill KV caches from OpenOrca, as test payloads |

## Trustworthy numbers

Every number carries its **measurement basis**. Mixing bases is how this repo
produced a "54 GB/s" D2H that does not exist.

### Host → device, on-device TSC (the wire)

| Path | Config | GB/s | Basis |
|---|---|---|---|
| SdkLayout direct, **io_loc pinned** | S=16, K=16384 | **11.43** | TSC, sync-aligned |
| SdkLayout direct, **io_loc pinned** | S=16, K=512 | 12.73 | TSC (peak) |
| SdkLayout direct, **auto io_loc** | S=16, any K | **~4.2 (plateau)** | TSC |
| memcpy `ch=16`, big grid 512×512 | k=2048, loop=5 | 9.20 | TSC |
| memcpy `ch=16`, small grid 64×16 | k=4096, loop=500 | ~5.2 | TSC, amortized |
| SdkLayout single PE (1×1) | e3.6 batched | 1.08 | TSC |

### Device → host, on-device TSC

| Path | Config | GB/s |
|---|---|---|
| SdkLayout direct, **pinned** | S=16, K=512 | 15.38 (peak) |
| SdkLayout direct, **pinned** | S=16, K=16384 | 12.54 |
| SdkLayout direct, **auto io_loc** | S=16, any K | ~4.3 (plateau) |
| memcpy `ch=16`, 64×16 | k=4096, loop=500 | ~4.77 |

### Host ↔ host (worker pod to worker pod, TCP over RoCE underlay) — `e5`

Sustained 10 s, hash-verified. **Scales linearly to S=16, then saturates.**

| Streams | 1 | 2 | 4 | 8 | 16 | 32 |
|---|---|---|---|---|---|---|
| GB/s | 0.632 | 1.222 | 2.537 | 4.880 | **8.713** | 8.743 |

Ceiling ≈ **8.7 GB/s** (~70% of 100 GbE line rate). Single flow ≈ 0.63 GB/s,
flat across 64 KiB → 16 MiB chunk sizes.

### Latency floors

| Path | p50 |
|---|---|
| SdkLayout 1×1, N=3 pipeline, T=8 fp32, lockstep (`e8`) | **0.977 ms** |
| SdkLayout 1×1, N=3, T=1024, lockstep (`e10`) | 0.85 ms |
| memcpy 16×16, N=3, T=1024, lockstep (`e10`) | 26.39 ms |
| controller↔worker `launcher.run("printf")` — bare gRPC floor (`e16`) | 2.4 ms |
| `SdkLauncher.run()` polling, FIFO source (`e9`) | 2.0 ms (p99 2.3) |
| `SdkLauncher.run()` polling, regular file (`e9`) | 3.5 ms (p99 5.6) |
| `SdkRuntime.memcpy_d2h` (deprecated, 502-regressed) (`e9`) | 1.42 ms |

## Measurement traps — read before quoting any number

These produced multiple wrong conclusions in this repo. Each is confirmed by a
sweep, not a hypothesis.

**1. Loop count inflates D2H and deflates H2D.** Same config
(`m=64 n=16 k=4096 ch=16`), only `--loop-count` varies:

| loop | 5 | 20 | 100 | 500 |
|---|---|---|---|---|
| H2D GB/s | 4.32 | 4.66 | 5.21 | 5.18 |
| D2H GB/s | **54.72** | 5.92 | 4.85 | **4.77** |

The famous **"54.6 GB/s D2H"** in `h2d_playground_overview.md` is the
`loop=5` reading. It is above any plausible NIC ceiling and it is **wrong**;
the amortized value is ~4.8 GB/s. Always report the loop count. H2D moves the
opposite way because fixed setup amortizes as loops grow.

**2. TSC ≠ host-wall, and both are "real".** TSC measures the wire; host-wall
measures the wire plus the host's ability to feed it. At S=16 pinned, K=16384:
TSC **11.43 GB/s**, host-wall **7.43 GB/s**. There is also a ~140–150 ms fixed
host floor: at K=32 host-wall reads 0.057 GB/s while TSC reads 5.04 GB/s. Small-K
host-wall numbers are almost entirely setup.

**3. `memcpy_h2d` returns on queue submission, not wire completion.** `e1`'s
"warm projection" of **20.7 GB/s** at `ch=16` is host-wall and fictitious; the
TSC-instrumented run on the same grid says **3.3 GB/s**.

**4. `runner.launch(nonblock=False)` returns before the kernel finishes.** The
following `memcpy_d2h` blocks on completion, so kernel time silently lands in
the `d2h` column. In `e7` at R=10000, `d2h_ms` reads 9.17 ms of which ~7 ms is
kernel wait; true d2h is the R=1 baseline (~1.8 ms).

**5. `e7` converts cycles at 850 MHz.** The `cerebras-sdk-pe-timestamp-timing`
skill records **1.1 GHz** as the correct WaferEngine constant. `e7`'s absolute
`device_ms` column is therefore suspect by ~1.29×; its *relative* R-scaling
(the sanity gate) is unaffected.

**6. `e10`'s 31× speedup is not byte-matched.** memcpy pushed 1 MiB/iter over a
16×16 grid; SdkLayout pushed 4 KiB/iter over 1 PE. The comparison holds at
*per-PE payload*, which is the streaming-decode metric, but it is not a
throughput comparison. Say which you mean.

## Transport choice: memcpy vs SdkLayout direct streams

|  | memcpy framework | SdkLayout direct link |
|---|---|---|
| Compile | `cslc --memcpy --channels=N` | `SdkLayout.create_input_stream/...` |
| Host API | `memcpy_h2d` / `memcpy_d2h` | `runtime.send()` / `receive()` |
| Fabric cost | 3 west + 2 east columns reserved | demux/mux columns you build |
| Scatter/gather | built in | **your responsibility** (1 stream = 1 PE) |
| RTT vs payload T | **linear**: `0.025·T + 0.76 ms` | **flat**: `0.0002·T + 0.63 ms` |
| Per-pipeline-stage cost | 12.98 ms | 0.33 ms |
| Artifact reuse across processes | yes (offline compile) | **no** — see below |

**Rule of thumb:** bulk weight loading and big grids → memcpy. Token-by-token
decode, small payloads, deep pipelines → SdkLayout direct streams.

`create_input_stream()` / `create_output_stream()` attach to **exactly one PE**
on a physical wafer-edge port. Fan-out to a multi-PE region is the user's job
(the demux/mux or "supercolumn" pattern).

## The five load-bearing knobs

Each is a one-line change worth a large multiple.

1. **Pin `io_loc` explicitly.** Auto-pick clusters the ports and caps S=16 at
   ~4.2 GB/s (TSC). Pinning → 11–15 GB/s. Skill:
   `wse-sdklayout-multistream-io-loc-pinning`.
   *Disambiguation:* [[prefill-decode-transfer-bandwidth]] records io_loc as
   **refuted** — that was io_loc as a cause of a *device hang* (the placements
   were valid). It is not a claim about bandwidth. Auto-placement is valid **and**
   slow; both statements are true.
2. **`--h2d-sub-batch-wavelets=65536`.** Split each per-stream `runtime.send`
   into 256 KB sub-batches issued `nonblock=True` back-to-back. With `=0` (one
   big send per stream), aggregate collapses to **80–140 MB/s**. `e14` calls
   this LOAD-BEARING and defaults it on.
3. **`order=MemcpyOrder.COL_MAJOR`** for every memcpy h2d/d2h. COL_MAJOR *is*
   wire order (the engine streams depth-by-depth across the PE width);
   ROW_MAJOR forces a cache-hostile host-side strided transpose that caps at
   ~2.7 GB/s. Measured on `1024×512 ch16`:

   | payload | ROW_MAJOR | COL_MAJOR | speedup |
   |---|---|---|---|
   | 256 MiB | 281 ms | 63 ms | 4.5× |
   | 1 GiB | 1343 ms | 244 ms | 5.5× |
   | 2 GiB | 2540 ms | 519 ms | 4.9× |

   Both scale linearly with bytes (intercept ≈ 0) → the penalty is per-byte, so
   batching calls would not have helped. Safe only when the kernel is
   layout-agnostic (element-wise) or the on-chip placement matches.
4. **Pick the right NIC** (see cluster facts below). Wrong NIC = 8× loss.
5. **Lockstep (`--max-in-flight=1`).** Counterintuitively *reduces* RTT on both
   transports (~5.7–5.9 ms saved at canonical) because backed-up frames contend
   at the ingress LVDS port. Also **`--flows-per-edge=1`**: multi-flow regresses
   SdkLayout severely (0.85 → 3.59 ms going to M=16) with no payload to
   amortize.

## CS-3 (EPCC) cluster ground truth

Verified across `e5`, `e11`, `e13`, `e14`, `e16`. These are deployment facts,
cheap to get wrong and expensive to rediscover.

| Fact | Consequence |
|---|---|
| Worker pod has **two NICs**: `net1` underlay `10.27.x.x/22` (Multus) and `eth0` overlay `100.64.x.x/32` | The overlay runs at **~110 MB/s**; the underlay at ~9 GB/s. Bind to the underlay. |
| **Only `psutil` sees `net1`** | `socket.gethostbyname()` and friends return the overlay. Use the e5-style psutil IP picker; `rdv.json`'s `ips` must list `10.27.x.x` **first**. |
| Two Mellanox ConnectX-5 HCAs (`mlx5_0`, `mlx5_1`), 100 Gb/s, `link_layer=Ethernet` (RoCE) | Verbs devices exist and are `0666` — no root needed. |
| **`/home` does NOT mount in SdkLauncher pods** (it does in `csrun_cpu`/training pods) | No shared-FS channel from a launcher pod. `HOME=/`, no nfs/ceph/fuse mounts. |
| Worker→controller TCP **blocked**; worker has **zero egress** except SDK gRPC to `10.27.24.65:443` | No direct exfil path from a pod. |
| Controller→worker **UDP forward is OPEN**; return is **BLOCKED**; TCP is **dead** | Gateway SNATs controller traffic into `10.24.x`. A sub-ms one-way push *into* the worker is plausible; nothing comes back. |
| Worker↔worker underlay TCP works (~8.7 GB/s at S=16) | Pod-to-pod is the only fast host link. |
| **Controller node has no `/dev/infiniband`** (plain virtio OpenStack VM) | RoCE controller↔worker is permanently dead. Workers have verbs; the controller does not. |
| `InconsistentVersion … client 1.14.0 vs cluster server 1.13.2`, `Could not find coordinator IP:port`, `Empty ingress service url` | **Benign preamble.** All three appear verbatim in runs that then succeed. Confirmed across every `e5` result log. |
| EPCC ingress returns sporadic **HTTP 502** on `SdkLauncher.run()` | ~5 across a 49-row sweep. Recovery = re-run; guard sweeps with skip-if-summary-exists. |
| Cluster ceiling **N ≤ 4 chips** | Pipeline-depth experiments cannot exceed N=4. |
| Adding a pipeline stage is **super-linear** | `e14`: e2e RTT 0.774 / 1.748 / 3.040 s for N=1/2/3; per-stage wall itself grows 0.78→0.96→1.13 s because all pods share the RoCE fabric. Fit `RTT(N) ≈ 0.16·N² + 0.50·N + 0.12` s (3 points — thin). |

## SDK / API gotchas hit in this series

- **`SdkCompileArtifacts(out_dir).load()` fails for SdkLayout** with
  `wio_flow_it.find("flow-id") != end()`. The `port_map` metadata only exists on
  the in-process `layout.compile()` return value. Consequence: each pipeline
  stage must **build + compile + run in one process** (~30 s per stage), so the
  offline-compile-then-dispatch pattern that works for memcpy does not work here.
- **Let colors auto-assign** — drop the second arg to `core.color(name)`. Pinning
  to 0/1 collides with SDK auto-generated io_port colors:
  `Inconsistent fixed constraints …`.
- **Use the port-based stream API**, not `*_from_loc`. `_from_loc` demands
  explicit physical color IDs and fails with
  `I/O port color 'core_in_color' expected to have an explicit physical value`.
- **Output ports need an even wavelet count** → `T=1` is not compilable for
  SdkLayout (`e10` permanently skipped that row).
- CSL always compiles against the **full fabric** (WSE-3: `762×1172`).
  `cslc`/`SdkCompiler` need `--fabric-dims=762,1172` explicitly; `SdkLayout`
  inherits dims from the `SdkExecutionPlatform` object automatically.
- A local task named `compute()` **shadows** an imported module binding
  `const compute = @import_module(...)`. Rename the import.

Existing granular skills cover several of these: `cerebras-sdk-1-13-2-binding-quirks`,
`cerebras-sdk-direct-stream-tsc-sync-tic-toc`, `cerebras-sdk-tsc-vs-hostwall-diagnostic`,
`cerebras-memcpy-grid-size-dominance`, `cerebras-sdk-fast-fp16-h2d`,
`cerebras-sdk-pe-timestamp-timing`, `wse-sdklayout-multistream-io-loc-pinning`.

## Latency decomposition (`e7`, N=3 K=64 T=1024 R=1, 1 MiB/iter)

| stage | recv | h2d | device | d2h | send | total | e2e RTT |
|---|---|---|---|---|---|---|---|
| 0 ingress | 0.11 | 0.59 | 0.001 | 1.81 | 6.15 | 8.70 ms | **58.82 ms** |
| 1 middle | 6.04 | 0.55 | 0.001 | 1.77 | 0.47 | 8.85 ms | – |
| 2 egress | 6.07 | 0.56 | 0.001 | 2.03 | 0.48 | 9.17 ms | – |

- **On-device compute is rounding error** at R=1 (1 µs vs ~9 ms of comm). The
  wafer idles while the host ships bytes.
- **Host↔host TCP dominates**: ~6 ms/iter, of which only ~1.6 ms is wire
  (1 MiB ÷ 0.634 GB/s); the rest is back-pressure.
- **e2e RTT / max-stage-wall ranges 1.9×–9.8×, not N.** The naive
  "frame traverses N stages" model is wrong: queueing grows with K, and the ack
  channel travels back through every forwarding stage.

## The supercolumn topology (`e11`)

One LVDS stream feeds one supercolumn: a `dispatch_pe` column (x=1) with
`_Y_STRIDE=18` between rows, each dispatch PE peeling 16 chunks east into a
16-PE compute row chain and forwarding the rest south. The 17 gap PEs between
dispatch rows are **auto-painted SOUTH-passthrough** by `layout.connect()` — no
code on them.

- **Steady-state bottleneck is `dispatch[0]`'s RAMP**: it handles 64 chunks/iter
  in (16 east + 48 south) and 128 counting the mirrored output path, while
  `dispatch[3]` handles 32. That asymmetry is the chain-serialization caveat.
- **Why the two-color checkerboard:** on a single PE a given color is
  **unidirectional** — it can carry an input queue or an output queue, not both.
  A PE that must consume from west *and* relay east therefore needs a second
  color. Two colors alternating by PE parity is the minimum that makes every
  (PE, color) pair unambiguous. The wavelet flips color at each hop.
- **`SUPERCOLUMN_ANALYSIS.md` §3 documents the README contradicting the code**
  (gap PEs, color counts, color budget). Trust the code.

## Dead ends (do not re-chase)

- **RDMA-Write on EPCC** (`rdma-explore`): HCAs and verbs work, but the pod is a
  stripped dev environment — no `perftest` (`ib_write_bw`), no UCX, **no
  libibverbs/librdmacm C headers**, empty `ldconfig` cache. `ibv_rc_pingpong`,
  `rping`, `gcc` 8.3.1 and `clang` 14.0.5 *are* present. Path forward is either
  a crude `ibv_rc_pingpong -s -n` ballpark (zero code) or cross-compiling a
  static bench on the controller. Expected payoff ~8–11 GB/s and 1–3 µs/op vs
  TCP's 0.55 GB/s. **Never measured.**
- **Direct controller↔worker transport** (`e16`, CONCLUDED): TCP dead, UDP
  one-way only, RoCE impossible (controller has no HCA). The 2.4 ms
  `launcher.run()` gRPC round trip **is** the floor. Sub-1 ms *out* of a worker
  is not reachable on this deployment.
- **Mux fan-in, buffer pools, `TCP_NODELAY`, phased-iter, ack-relay**
  (dropped in `e14`): each was measured neutral once the NIC bug was fixed.
  `e14` cut ~6000 LOC to ~1900 by deleting them.
- **`e15-sdklayout-streaming` is a plan, not code.** Nothing there runs.

## Commands / paths

```bash
# Fetch the playground (it is NOT on main)
git fetch origin lexu/h2d-explore
git ls-tree -r --name-only origin/lexu/h2d-explore -- h2d-playground

# The canonical clean reference implementation — start here
h2d-playground/e14-clean-sdklayout/       # ~1900 LOC; compile.py + dispatch_pipeline.py + pipeline_stage.py
h2d-playground/e11-sdklayout-fanout/SUPERCOLUMN_ANALYSIS.md   # the topology/routing mechanism doc
h2d-playground/h2d_playground_overview.md                     # headline table — CONTAINS THE 54 GB/s ARTIFACT
h2d-playground/h2d_playground_overview_caveats.png            # the author's own caveat list

# memcpy COL_MAJOR 2 GiB reference benchmark (e14)
python compile.py --transport memcpy --width 512 --height 1024 --tile-len 1024 \
    --channels 16 --width-west-buf 30 --width-east-buf 30 --num-streams 16 --k-max-iters 128
python dispatch_pipeline.py --num-stages 1 --num-iters 8 --cache-input --no-kernel --skip-verify
```

## Open questions

- The overview table and the author's caveat note both report **7.38 GB/s** H2D
  for `ch16 m512×n512`, but `bandwidth-test/logs/m512-n512-k2048-...-h2d-loop5.txt`
  reads **9.20 GB/s**. Different loop counts / runs — needs disambiguation
  before either is quoted.
- `bandwidth-test-parallel` H2D and D2H both **regress at K=32768**
  (H2D pinned: 11.43 GB/s at K=16384 → 7.83 at K=32768; host-wall 578 ms →
  2119 ms for 2× the data). Cause unknown; suspect host memory pressure /
  page faults, not fabric.
- `e7`'s absolute `device_ms` used 850 MHz. Re-derive at 1.1 GHz if those
  numbers are ever load-bearing.
- RDMA-Write was never benchmarked (headers blocker). The 10×-BW /
  1000×-latency claim is an **expectation**, not a measurement.

## Last updated

2026-07-08
