# WaferEngine-staging Manual Conflicts

Last reviewed: 2026-07-29

## Needs Le/manual resolution

- **2026-07-29 — an in-repo "Failed approaches" entry appears to be wrong, and the
  correction is unconfirmed.** `PROGRESS.md` records that PR #14 demoted the `e2e` on-chip
  KV relay to inert filler, not config-revivable. A direct diff says otherwise for `e2e`
  (three `KV_TRANSFER: 1` configs already shipped on `main`; `build_relay` identical apart
  from whitespace; `src/relay.csl` still present at PR #14) — the claim holds only for
  **`e2e-pdSeparate`**. It looks like a model mix-up. **Not confirmed by Le**, and it
  changes an adopt-vs-port input in the convenient direction (adoption costs *less* than
  recorded), which is exactly when a correction deserves a second pair of eyes. See
  [[standalone-vs-integrated-kernel-parity]].
- **2026-07-29 — two in-repo contract lines are now known-stale and were not edited.**
  `milestones/M1-intra-pe-reuse.md § S0.2` says *"slot empty ⇔ `iter_num_bank[layer][slot]
  == 0`"*, but occupancy is a **host** judgement under D4; and the grep checklist lists S1
  as the owner of adding that dimension, which should read "not needed, superseded". Left
  for whoever next edits that milestone — flagged so it is not re-derived from the doc.
- *(Resolved this pass, recorded for traceability)* `memory/project.md` carried
  **"Real Qwen3 weights are NOT wired into any model"**. True for the standalone kernels
  and the `main`-line fused models; **false for `e2e-pdSeparate` at PR #14**, which bakes
  real HF weights and has now been run end to end on real WSE-3. Corrected in place with
  the scope made explicit.

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
