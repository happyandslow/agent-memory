# WaferEngine-staging Plan

Human-maintained roadmap and durable progress narrative. This is the canonical home for project goals, milestones, decisions, and next actions. Generated/current status belongs in `tracking/status.md`.

## Goals

- Understand qwen3-1.7B end-to-end serving variants on WSE-3: fused `e2e`, host-bridged `e2e-pdSeparate`, and their relationship to newer standalone decode/prefill kernels.
- Quantify KV-cache preserve-vs-evict/offload tradeoffs for WSE-3, including in-place, in-bank, idle-PE, host-DRAM, and recompute tiers.
- Measure effective prefill→decode KV handoff bandwidth honestly, counting both on-fabric movement and on-PE gather/transpose/re-layout compute.

## Milestones

- [x] e2e fused first CS-3 device PASS on mock weights; static geometry/floorplan recorded for prefill→decode transfer.
- [x] pdSeparate max-context and large-context prefill SRAM failure documented.
- [x] KV preserve/evict tier ladder captured, including Le's T0.5 in-bank reuse addition and force-decode-in-place direction.
- [x] Standalone-vs-integrated kernel parity gap documented.
- [ ] Instrument prefill→decode transfer segments A/B/C with TSC and compute first effective-GB/s number.
- [x] Resolve pre-S6 KV-management abstraction question: shared compute exists, but retain cannot be abstracted into integrated kernels until S4/S5 lifecycle port.
- [ ] Scope forced-token decode, T0.5 in-bank reuse, and T1 idle-PE offload prototypes.
- [ ] Decide whether fused e2e should carry prefill's sampled token into decode (host hop or new on-chip `pf_ht_tail` → HT_head wire) before making end-to-end accuracy claims.

## Decisions

| Date | Decision | Rationale | Link |
| --- | --- | --- | --- |
| 2026-07-05 | Treat integrated e2e/pdSeparate as older snapshots, not the serving source of truth. | Standalone kernels carry newer multi-round, runtime-varlen, chunked-prefill, EOS, softmax, and oracle fixes that integrated copies lack. | `memory/topics/standalone-vs-integrated-kernel-parity.md` |
| 2026-07-05 | Frame KV preserve-vs-evict as a tier ladder, not a binary on-chip/off-chip choice. | T0/T0.5/T1/T2/T3 have different reuse costs, capacity, and kernel support requirements. | `memory/topics/kv-cache-policy-tradeoffs.md` |
| 2026-07-06 | Count both transfer and transform compute in prefill→decode bandwidth. | The handoff is not a flat memcpy; gather, transpose, re-layout, seam shift, and decode cache writes all contribute to wall time. | `memory/topics/prefill-decode-transfer-bandwidth.md` |
| 2026-07-06 | Use WSE-3 TSC at 1.1 GHz for the e2e segment timing design. | The SDK bandwidth-test's 0.85 GHz constant is wrong for WaferEngine; the timing skill was updated with the project-specific reconciliation. | `memory/topics/prefill-decode-transfer-bandwidth.md` |

## Next actions

- [ ] Instrument `qwen3_1p7b-e2e` segment timings: t0 `start_kv_transfer`, t1 prefill states 0–3 done, t2 north-shift done, t3 decode `kv_flush_then_init`; validate in sim then on a device-sized config.
- [ ] Fill byte totals for the 2×2 configs from run printouts (`bsz`, `kv_dim_per_pe`, `seq_len_per_pe`, `max_layers_per_block`) so GB/s denominators are explicit.
- [ ] Compare fused on-chip seam path against pdSeparate host-DRAM bridge under the same both-segments-counted metric.
- [ ] Quantify T1 idle-PE offload and scope forced-token decode / T0.5 in-bank reuse.
- [ ] Discuss the no-keyed-routing/static-orchestration framing as a design constraint for KV reuse/tiering; check whether any retained-store or bridge mechanism implicitly assumes content routing.
- [ ] Unblock pdSeparate long-context prefill by shrinking/removing the quadratic score buffer; defer real HF weights/tokenizer/oracle unless Le reprioritizes them.
- [ ] Redraw/annotate `assets/prefill-decode-transfer/e2e-topology-full.svg`: x131 is a decode west strip, and x644 (the real east strip in 2×2) is currently absent.
- [ ] Fix e2e source/documentation hygiene found in the 2026-07-09 read: stale `route_calc.csl:5` axis comment, prefill vocab-padding asymmetry, K-pipe alias invariant check, and `csl_color_audit` raw `@set_config` parsing.

## Narrative progress log

### 2026-07-18

- Drained `memory/inbox/2026-07-16-fabric-no-keyed-routing-orchestration.md` into `memory/topics/csl-control-payload-mechanisms.md`. Durable framing: WSE fabric has no keyed/content routing; KV gather and related ML communication patterns are static topologies driven by deterministic steppers/rotations/chains. Added a follow-up to discuss how this constrains KV reuse/tiering designs.
- Moved generated all-kernel state-machine aggregate indexes from `memory/inbox/` to `assets/kernel-algo/` and updated `memory/topics/qwen3-kernel-analysis-atlas.md` so they stop appearing as un-drained captures.


> **Canonical M0 plan/state lives in the in-repo durable docs** (`ROADMAP.md`, `PROGRESS.md`,
> `milestones/M0-reuse-foundation.md`) per repo precedence; entries below are background.

### 2026-07-13

- Drained `memory/inbox/2026-07-13-kv-management-abstraction-design.md` into `memory/topics/s6a-decode-kv-retain.md` and corrected the parity-topic pointer. Durable decision: KV compute is shared enough to keep the seam isolated, but integrated kernels lack the runtime multi-round lifecycle where retain attaches, so S6 stays standalone-first and extraction waits for S4/S5. Prefill retain is viable as a `start_chunk` warm-start; force-decode remains an M2 mechanism.

### 2026-07-12

- **M0/S3 keyed KV store skeleton designed** (design-only; awaits Le's review before S4–S6 coding).
  Resolved for M0: key = **request id**, granularity = **whole-blob/exact key**, storage =
  **host-side keyed retained pool**, plus a **retrieve-by-key API**. Prefix-hash content key +
  token-vs-block match parked to M1 (block-constrained). Full design in
  `milestones/M0-reuse-foundation.md § S3`; background folded into
  `memory/topics/kv-cache-policy-tradeoffs.md` (2026-07-12 Updates).
- **Mechanism vs policy separation (Le):** M0 delivers the on-chip KV *sharing mechanism*; policy
  (hit detection, eviction) is deferred and not needed yet (M0/M1 use self-constructed artificial
  token ids). **New placement axis surfaced (was missing from GOALS): where the store + eventual
  policy runs — host (P1) / on-chip all-PEs (P2) / on-chip entrance PE (P3).** All three **open,
  nothing rejected**; host **for now** (least-effort, mechanism-only). SDK v2.10 note: on-PE allows
  only a compile-time integer-keyed table (no map/heap/strings/recursion). Escalated to `GOALS.md §7` + WS4.
- Prior M0 work (background): S1 status re-check gate (2026-07-11) and S2 PR#14 port contract
  (2026-07-11) — see `topics/pr14-real-serving-port-contract.md`.

### 2026-07-09

- Drained `memory/inbox/2026-07-09-e2e-kernel-qa-log.md` into `memory/topics/e2e-kernel-dataflow-and-topology.md` plus this plan. Durable finding: fused e2e carries KV state on-chip, but decode step 0 is seeded by host/config token ids rather than prefill's sampled first token.
- Captured decode topology details: demux/HT_head seams, K-pipe strip mechanics, forced color aliasing, latent `P_Y_BLOCK_NUM >= 4` west-strip hazard, and the new `assets/decode-kpipe/kpipe-south.svg` diagram.
- Recorded the delegated tensor-layout reference under `assets/data-layout/`, including the decode/prefill axis rotation and follow-up source-cleanup items.

### 2026-07-06

- Drained `memory/inbox/2026-07-06-prefill-decode-transfer-bandwidth.md` into this plan and `memory/topics/prefill-decode-transfer-bandwidth.md`. The durable finding is that the fused e2e KV handoff has three timed pieces — prefill gather+transform, north seam shift, and decode receive+cache write — and effective bandwidth must include the compute-heavy transformations, not just wire time.
- Preserved the timing mechanism/design update: use per-PE TSC (`<time>`, 48-bit, 1.1 GHz), first split segments per PE, then cross-PE reference-corrected end-to-end GB/s.
- Converted `memory/context.md` and `tracking/status.md` into thin generated projections pointing here and to topic notes.

### 2026-07-05

- KV-cache policy tradeoff and standalone-vs-integrated parity topics captured the main research framing for preserve/evict work.
