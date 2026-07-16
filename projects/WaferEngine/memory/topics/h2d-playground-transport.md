---
summary: CS-3 host/device and cross-pod transport experiments from h2d-playground.
tags: [waferengine, cs3, h2d, transport, rdma, latency]
---

# h2d-playground transport experiments

## Summary

The `lexu/h2d-explore/h2d-playground/` experiments measure CS-3 host↔device, host↔host, and RDMA transport behavior. The compact source is `docs/2026-07-14-h2d-playground-experiments.md`; this topic preserves load-bearing guidance for future WaferEngine/WaferServe work.

## 2026-07-14 findings

- Use on-device TSC for device drain/emit timing. Host-wall memcpy can read as high as ~27 GB/s while true small-grid per-PE drain is closer to ~3 GB/s because queue/lifecycle overhead is folded into host measurements.
- A single direct `SdkLayout` stream is about 1.08 GB/s; scaling requires `io_loc` pinning. Sixteen pinned streams reach roughly 11–15 GB/s, while auto-placement can cap near 4 GB/s. Large grids unlock memcpy H2D (512×512 around 9.2 GB/s), but D2H may collapse (~1.88 GB/s).
- Cross-pod host-fabric TCP only performs on the 10.27.x underlay: one flow ~0.63 GB/s, sixteen flows ~8.7 GB/s aggregate. The 100.64.x Kubernetes overlay caps around 110 MB/s/connection; workers have no shared FS and no egress.
- Pipeline decode latency is dominated by host↔host TCP and queueing, not compute. Lockstep one-frame-in-flight is the main latency knob: the measured small-payload regime lands around 10–15 ms/token decode at 8 KiB/token.
- In the pipeline, `SdkLayout` usually beats memcpy because framework-call cardinality dominates; at matched wire bytes they tie when stream count is tuned. Prefer one stream at T≈8 where the experiment measured ~0.96 ms/token (~1040 tok/s).
- Controller↔worker is asymmetric: fast one-way UDP into workers is possible on the underlay, but worker egress is absent. Fastest supported controller round trip is `launcher.run("printf")` at ~2.4 ms p50; streaming poll floors were ~3.5 ms batched / ~2.0 ms FIFO single-token.
- Controller-direct 2 GiB→device is stage-bound rather than wire-bound: device memcpy can drain at ~10.6 GB/s, but one-time runtime init is ~58 s and recurring `launcher.stage` is ~20–30 s (~90–110 MB/s) and does not parallelize.
- RDMA works and reduces small-message latency/CPU (about 7.8 µs vs 65 µs at 4 KB; parity near ≥16 MB at ~12.3 GB/s line rate) but it does not address the KV-handoff bottleneck.
- `orca_kv_pack_mini` provides a KV-cache file format plus a 200-prompt OpenOrca corpus; bf16 footprint was ~131 KB/token.

## Pointers

- Full reference: `docs/2026-07-14-h2d-playground-experiments.md`.
- Drained from `memory/inbox/2026-07-14-h2d-playground-summary.md`.
