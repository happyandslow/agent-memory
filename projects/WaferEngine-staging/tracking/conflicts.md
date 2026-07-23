# WaferEngine-staging Manual Conflicts

Last reviewed: 2026-07-23

## Needs Le/manual resolution

- No contradictory project facts found during 2026-07-22 maintenance.

## Promotion candidates / manual follow-up

- 2026-07-22: Consider promoting the retain-review heuristic "distinguish carried-over state from state recomputed from a carried counter" to a recurring CSL/retain review skill.
- 2026-07-22: Consider updating the `cs3-runner` skill for ssh transport death: `rc=255` can bypass `csctl cancel`; check for orphan wafer jobs on reconnect.
- 2026-07-22: Consider updating the TSC/device-staging guidance: this e2e model's `cslc_bin` inline cap breaks `<time>.get_timestamp`, and new `.csl` files must be added to `FILES_TO_STAGE`.
- 2026-07-22: Consider promoting/atlas-linking the prefill metainfo review heuristic: per-request metainfo rides two channels (i32 token-id prepend + fp16 X-tile append), bridged at `ht_head`, so widen both paths together.
- 2026-07-23: Consider updating the `csl-color-audit` skill/docs with decode-layout caveats: predicted floorplans can include spurious fused-prefill regions, narrow helper PEs render as badges/side-table rows, and the matrix view omits switch/router helper PEs such as KV-ingress adaptor/injector/demux/mux tasks.
- 2026-07-23: Consider promoting the force-decode/F-dimension review heuristic: when adding a per-request count to a lock-step fabric loop, keep shared-color producer/consumer counts additive until both sides are deliberately mirrored; F=1 can hide an F>1 color imbalance.
- 2026-07-23: Consider promoting the performance-attribution heuristic from S6b: an F-sweep curve shape separates skip-compute (linear per forced step) from pipeline/resource fill (saturating/knee) better than a single mixed timing point.
