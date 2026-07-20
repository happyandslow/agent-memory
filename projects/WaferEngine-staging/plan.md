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
- [x] Bring up prefill warm-start (`START_CHUNKS` prefix reuse): byte-identical PASS in sim and on real WSE-3 after fixing three independent defects.
- [x] Re-measure the prefill prefix-reuse saving on real-dim device configs; real-scale WSE-3 results now show strongly sub-linear savings (25% reuse → 7.7%, 50% → 22.8%, 75% → 45.2%).
- [ ] Scope forced-token decode, T0.5 in-bank reuse, and T1 idle-PE offload prototypes.
- [ ] Decide whether fused e2e should carry prefill's sampled token into decode (host hop or new on-chip `pf_ht_tail` → HT_head wire) before making end-to-end accuracy claims.

## Decisions

| Date | Decision | Rationale | Link |
| --- | --- | --- | --- |
| 2026-07-05 | Treat integrated e2e/pdSeparate as older snapshots, not the serving source of truth. | Standalone kernels carry newer multi-round, runtime-varlen, chunked-prefill, EOS, softmax, and oracle fixes that integrated copies lack. | `memory/topics/standalone-vs-integrated-kernel-parity.md` |
| 2026-07-05 | Frame KV preserve-vs-evict as a tier ladder, not a binary on-chip/off-chip choice. | T0/T0.5/T1/T2/T3 have different reuse costs, capacity, and kernel support requirements. | `memory/topics/kv-cache-policy-tradeoffs.md` |
| 2026-07-06 | Count both transfer and transform compute in prefill→decode bandwidth. | The handoff is not a flat memcpy; gather, transpose, re-layout, seam shift, and decode cache writes all contribute to wall time. | `memory/topics/prefill-decode-transfer-bandwidth.md` |
| 2026-07-06 | Use WSE-3 TSC at 1.1 GHz for the e2e segment timing design. | The SDK bandwidth-test's 0.85 GHz constant is wrong for WaferEngine; the timing skill was updated with the project-specific reconciliation. | `memory/topics/prefill-decode-transfer-bandwidth.md` |
| 2026-07-19 | Keep every per-column x-chain payload EVEN (`metainfo_len = 4` = 3 real + 1 pad). | An odd-extent async `fabin → fabout` `@mov16` never fires its completion callback on WSE-3 and silently deadlocks the block; an isolated 8-PE reproducer ruled out queue depth. | `memory/topics/s6a-prefill-warm-start.md` |
| 2026-07-19 | Treat the mock-scale prefill reuse numbers as mechanism-only; no reuse-value claim until real-dim configs are re-measured. | Saving tracks (k/n)² rather than k/n, so prefix reuse has strong diminishing returns — but the grid ran at dim=64/vocab=64, and the L=2048 rows were invalidated by a host cache-key bug. | `memory/topics/s6a-prefill-warm-start.md` |
| 2026-07-20 | Model prefix-reuse value with position weighting, not linear hit rate. | Real-scale WSE-3 results show 50% prefix reuse saves only 22.8% latency and 75% saves 45.2%; reused prefix chunks are the cheapest part, while recomputed suffix chunks dominate. | `memory/topics/s6a-prefill-warm-start.md` |
| 2026-07-20 | Decode retain's benefit is skipping already-executed decode steps, not making each equal-work step cheaper. | Equal-work decode comparisons differ by only ~0.02% fixed overhead; the correct end-state comparison saves 34.6% total decode work by avoiding redoing discarded steps. | `memory/topics/s6a-prefill-warm-start.md` |

## Next actions

- [ ] Finish the in-flight long-sequence follow-up: k>0 prefill reuse points at L=16,384 and the decode L=4096 pair after CS-3 cluster recovery; tee every per-point device log because `out_*` artifact dirs do not return from worker nodes.
- [ ] Review and commit the S6a-prefill working tree: three fixes (metainfo even-padding, `ht_head` chunk-slot indexing, two host `start_chunk` assumptions) are unlanded on `lexu/staging/s6a-inner-pe-kv-route-a`.
- [ ] Strengthen the warm-start gate so it fails when reuse silently never engages — byte-identical KV alone also passes a cold run.
- [ ] Decide whether to lift decode's `MAX_SEQ_LEN ≤ 1016` wall; it needs a KV access/layout change that keeps the traversal stride inside the DSD's i8 `.stride` field, not a type widening.
- [ ] Instrument `qwen3_1p7b-e2e` segment timings: t0 `start_kv_transfer`, t1 prefill states 0–3 done, t2 north-shift done, t3 decode `kv_flush_then_init`; validate in sim then on a device-sized config.
- [ ] Fill byte totals for the 2×2 configs from run printouts (`bsz`, `kv_dim_per_pe`, `seq_len_per_pe`, `max_layers_per_block`) so GB/s denominators are explicit.
- [ ] Compare fused on-chip seam path against pdSeparate host-DRAM bridge under the same both-segments-counted metric.
- [ ] Quantify T1 idle-PE offload and scope forced-token decode / T0.5 in-bank reuse.
- [ ] Discuss the no-keyed-routing/static-orchestration framing as a design constraint for KV reuse/tiering; check whether any retained-store or bridge mechanism implicitly assumes content routing.
- [ ] Unblock pdSeparate long-context prefill by shrinking/removing the quadratic score buffer; defer real HF weights/tokenizer/oracle unless Le reprioritizes them.
- [ ] Redraw/annotate `assets/prefill-decode-transfer/e2e-topology-full.svg`: x131 is a decode west strip, and x644 (the real east strip in 2×2) is currently absent.
- [ ] Fix e2e source/documentation hygiene found in the 2026-07-09 read: stale `route_calc.csl:5` axis comment, prefill vocab-padding asymmetry, K-pipe alias invariant check, and `csl_color_audit` raw `@set_config` parsing.

## Narrative progress log

### 2026-07-20

- Drained `memory/inbox/2026-07-19-prefill-prefix-reuse-real-scale-perf.md` into `memory/topics/s6a-prefill-warm-start.md` and this plan. Real-scale WSE-3 prefill prefix reuse is now measured at Qwen3-1.7B dims / 524,288 PEs / L=8192: 25% reuse saves 7.7%, 50% saves 22.8%, and 75% saves 45.2% (all byte-identical). Prefix reuse is strongly sub-linear in hit fraction because it skips the cheap early chunks and recomputes the expensive suffix.
- Corrected decode interpretation: retain does not make an equal-work decode step cheaper (~0.02% bookkeeping overhead); it saves by skipping already-executed decode steps. Correct real-scale end-state comparison saves 34.6% total decode work.
- Captured operational guardrail for device measurements: per-point stdout logs are the durable result because `out_*` artifact dirs stay on worker nodes; quote host wall only as context, not latency.

### 2026-07-19

- Drained `memory/inbox/2026-07-19-s6a-prefill-warm-start-bringup.md` into the new topic `memory/topics/s6a-prefill-warm-start.md` and this plan. **Prefill warm-start (`START_CHUNKS` prefix reuse) now executes and is byte-identical in sim and on real WSE-3** — it had never actually run before, because a fabric deadlock masked everything downstream.
- Three independent defects found and fixed: an odd-extent async `fabin → fabout` `@mov16` that silently deadlocks WSE-3 (isolated to an 8-PE reproducer, promoted to the `csl-odd-extent-fabric-forward-hang` skill); an `ht_head.csl` branch hardcoding chunk slot 0; and two host places that assumed `start_chunk == 0`, one of which silently ran warm requests cold.
- Capacity walls differ by kernel: prefill stops at `MAX_SEQ_LEN = 2048` on PE data memory plus task table, decode at 512/1016 because the DSD `.stride` field is `i8`. The decode wall is an ISA field width, not memory, and is unrelated to the similarly-sized ~512 prefill SRAM figure in `e2e-pdSeparate-device-validation.md`.
- Headline (mock scale only, **not** a performance result): prefill prefix-reuse saving tracks **(k/n)², not k/n** — the reused prefix chunks are the cheap ones. If it holds at real dim, prefix reuse has strong diminishing returns. Flagged as must-re-measure before use.

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
