# WaferEngine-staging Manual Conflicts

Last reviewed: 2026-07-27

## Needs Le/manual resolution

- No contradictory project facts found during 2026-07-22 maintenance.
- 2026-07-27 cron: left local meeting-file changes untouched because they appear human/app-owned and ambiguous: modified `meetings/2026-07-26.pptx` plus untracked Office temp file `meetings/~$2026-07-26.pptx`. Decide whether to keep, revert, or remove the temp file manually.

## Promotion candidates / manual follow-up

- 2026-07-22: Consider promoting the retain-review heuristic "distinguish carried-over state from state recomputed from a carried counter" to a recurring CSL/retain review skill.
- 2026-07-22: Consider updating the `cs3-runner` skill for ssh transport death: `rc=255` can bypass `csctl cancel`; check for orphan wafer jobs on reconnect.
- 2026-07-22: Consider updating the TSC/device-staging guidance: this e2e model's `cslc_bin` inline cap breaks `<time>.get_timestamp`, and new `.csl` files must be added to `FILES_TO_STAGE`.
- 2026-07-22: Consider promoting/atlas-linking the prefill metainfo review heuristic: per-request metainfo rides two channels (i32 token-id prepend + fp16 X-tile append), bridged at `ht_head`, so widen both paths together.
- 2026-07-23: Consider updating the `csl-color-audit` skill/docs with decode-layout caveats: predicted floorplans can include spurious fused-prefill regions, narrow helper PEs render as badges/side-table rows, and the matrix view omits switch/router helper PEs such as KV-ingress adaptor/injector/demux/mux tasks.
- 2026-07-23: Consider promoting the force-decode/F-dimension review heuristic: when adding a per-request count to a lock-step fabric loop, keep shared-color producer/consumer counts additive until both sides are deliberately mirrored; F=1 can hide an F>1 color imbalance.
- 2026-07-23: Consider promoting the performance-attribution heuristic from S6b: an F-sweep curve shape separates skip-compute (linear per forced step) from pipeline/resource fill (saturating/knee) better than a single mixed timing point.
- 2026-07-24: Consider promoting the host-side serving/control placement rule to repo convention docs or a review skill: while standalone kernel forms are still converging, per-kernel host control helpers belong beside `launch.py`; extract to `waferengine/engine/` only after compiled-kernel versioning settles.
- 2026-07-25: Consider updating the `meshagent-sync` skill/protocol: never `patch` a Markdown bulleted-list region in ContextBase/Outline mirrors because sibling list items can be silently dropped; re-mirror via header replace + append and verify mid-file plus late-file sentinels.
- 2026-07-25: Consider updating the `meshagent-sync`/checkpoint protocol to list/fetch existing same-day Logs and recent mirror `updatedAt` before creating a new session log or re-mirroring durable docs, to avoid duplicating parallel-session work.
- 2026-07-25: Consider promoting the git branch-status verification rule: before asserting commit/merge state, verify live branch topology and feature content; under squash merges, `merge-base --is-ancestor <original-tip>` can false-negative even when the branch contains the feature.
- 2026-07-26: Consider promoting the per-request-dimension review heuristic: before adding a slot/request axis to a lockstep kernel, identify which invariants the old uniformity enforced for free (for M1 decode, equal active-lane length survives only as a host/test obligation because scalar `iter_num` is also the packed score stride).
- 2026-07-27: Consider promoting the review heuristic from the mixed-hit/miss correction: before declaring a case impossible, check whether the impossibility came from an assumed implementation choice (take-over) rather than from hardware/kernel invariants (shared scalar/RoPE state).
- 2026-07-27: Consider promoting the negative-control testing rule: before trusting a red config/test PASS, prove it can fail; unknown config keys and empty-input comparisons must not silently degrade to positive controls.
