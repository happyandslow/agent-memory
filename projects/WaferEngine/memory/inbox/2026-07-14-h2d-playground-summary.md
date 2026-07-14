# h2d-playground experiment summary (branch lexu/h2d-explore)

**Date:** 2026-07-14
**Full doc:** `docs/2026-07-14-h2d-playground-experiments.md`

Compiled a single reference summarizing ~25 transport-bandwidth/latency experiment studies under
`happyandslow/WaferEngine:lexu/h2d-explore/h2d-playground/`. Also published as a nested doc set in
ContextBase (Hybrid Serve collection → Hybrid Communication & Observability topic thread).

Load-bearing conclusions (see full doc for numbers + per-experiment detail):

- **Measure with on-device TSC, not host-wall.** memcpy host-wall reads up to 27 GB/s but true per-PE
  drain is ~3 GB/s (small grids); host-wall folds in queue-submission/lifecycle overhead. Repeated across
  bandwidth-test, e1, e3.6, e3.7, e14.
- **Single SdkLayout direct stream = ~1.08 GB/s** (e3.6). Scaling needs **io_loc pinning**: 16 pinned
  streams ~11–15 GB/s, auto-placed caps ~4 GB/s (bandwidth-test-parallel). Big grid unlocks memcpy H2D
  (512×512 → 9.2 GB/s; D2H collapses to 1.88).
- **Cross-pod host-fabric TCP** (e5): single flow ~0.63 GB/s, 16 flows ~8.7 GB/s aggregate — but only over
  the **10.27.x underlay**; 100.64.x k8s overlay caps ~110 MB/s/conn (e13). No shared FS, no worker egress.
- **Pipeline latency** (e7/e8): compute negligible, host↔host TCP + queueing dominate. **Lockstep (1 frame
  in flight)** is the dominant knob: N=3 RTT 58.8→25.5 ms; at 8 KiB/token 0.977 ms/frame → ~10–15 ms/token
  decode. multi-flow/direct-ack don't help at small payload.
- **sdklayout vs memcpy in-pipeline** (e10): sdklayout wins 1.3×–31× (fixed-overhead-dominated). At
  **matched wire bytes** (e11 supercolumn) they tie once stream-count S is tuned — the cost is
  **framework-call cardinality, not wire bandwidth**; use S=1 at T~8 (0.96 ms/token ≈ 1040 tok/s).
- **Controller↔worker is asymmetric** (e16): fast one-way UDP in (sub-ms, underlay only), no path out;
  fastest supported round trip = single `launcher.run("printf")` ~2.4 ms p50. Streaming poll floor (e9):
  batched ~3.5 ms p50 (3k+ tok/s) / FIFO ~2.0 ms p50 single-token (172 tok/s).
- **Controller-direct 2 GiB → device** (e12): stage-bound, not wire-bound. Device memcpy 0.2 s (10.6 GB/s);
  costs are one-time SdkRuntime init ~58 s (amortized by warm server) + recurring launcher.stage ~20–30 s
  (~90–110 MB/s, does NOT parallelize).
- **RDMA** (rdma-explore): ~8× TCP at 4 KB → parity ≥16 MB (both ~12.3 GB/s line rate); durable win is
  latency (7.8 vs 65 µs) + near-zero recv CPU (rdma-event). Works but doesn't help the KV-handoff bottleneck.
- **orca_kv_pack_mini:** KV-cache file format + 200-prompt OpenOrca corpus; ~131 KB/token bf16 footprint.

Relates to existing topics: [[project_controller_worker_direct_transport]], [[project_memcpy_vs_launcher_iopipeline]],
[[project_rdma_latency_5us_reality]], [[project_epcc_worker_pod_nics]], pe-sram-memory-breakdown.
