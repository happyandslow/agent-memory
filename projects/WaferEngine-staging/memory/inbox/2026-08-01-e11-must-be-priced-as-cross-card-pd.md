---
date: 2026-08-01
project: WaferEngine-staging
tags: [m2, e11, pd-disaggregation, cross-card, cost-model, nc_service, decision]
---

# Pricing the re-prefill baseline (lane C0): the register's "free same-fixture comparison" is the wrong scenario — real PD is cross-card — 2026-08-01

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured

Refines the E11 rows in [[m2-experiment-register]] (which frame E11 as "full re-prefill,
same fixture, no code, a free comparison point"). That framing is only right for the wrong
scenario.

## The situation this applies to

You are about to price **lane C0** (evict a request's KV, on resume re-prefill the whole
`L_hist+L_new` from scratch and ship all its KV back) as an M2 comparison point. The
register says it is a free desktop recombination of already-measured curves (prefill_span +
egress + ingress from E5/E6). Le stopped this: **"E11 需要结合 nc_service 里面的跨卡实验来
reason PD 分离的场景."**

## Why the naive framing is wrong

There are two different "PD" scenarios and the register conflated them:

- **① same-wafer time-multiplex** (WaferEngine-staging today): prefill and decode share
  **one** wafer by time-slicing; KV goes through **local host DRAM, never a network.** This
  is what E5 (ingress) / E6 (egress) / S0 (host bridge ~0.16 s/prompt) measured. It is
  **not** true PD disaggregation.
- **② two-pod cross-card disaggregation** (nc_service Mode-B): prefill on pod A, decode on
  pod B, KV **crosses the network.** This is real PD, and its overhead is dominated by
  stages E5/E6 never see.

E11-for-real-PD must be priced against ②, and ② only adds a network wire + cross-pod control
RPCs on top of ①.

## The borrowed measured decomposition (use it; do not re-measure)

nc_service already priced the cross-card KV handoff on **real WSE-3** (Llama-3-8B, 128 MB KV,
TCP ×16). See [[../../../nc_service/memory/inbox/2026-07-09-kv-handoff-zerocopy-and-rdma-negative]].
One-time bring-up **18.7 s → 2.5 s** after two fixes; segments: egress (compute+D2H lumped)
~1520 ms · host transform 15.3 s→**352 ms** · serde encode ~167 ms · frame 18 ms · **wire
82 ms/128 MB (loopback)** · unframe 790→**23 ms** · repack ~34 ms · H2D+first window ~637 ms ·
steady resume ~18 ms.

Two conclusions that both nc_service and WaferEngine reached independently, and that set the
E11 design:

1. **Wire is cheap; host serde/transform + on-chip D2H/H2D dominate.** "RDMA works but does
   not help" — the wire is only ~82 ms of a ~2.2 s handoff, so TCP (2196 ms) vs RDMA
   (2283 ms) is statistically indistinguishable. **RDMA is not the lever;** do not treat it
   as the win in T2.
2. The large host-serde numbers (790→23, 15.3 s→352 ms) are **implementation-level Python
   artifacts, model-independent, mostly already fixed** — not physical costs.

## The decision (Le-approved: "E11 先做 T1 然后做 T2")

E11 is **a cost-model synthesis, not a port.**

- **T1** (desktop, ≈0 wafer hours): compose WaferEngine's own measured on-chip legs (E5/E6/
  E7) + nc_service's borrowed cross-card decomposition, **scaled Llama 128 MB → Qwen ~32 MiB
  (fixed costs do NOT scale linearly)**, everything tagged measured / borrowed-scaled /
  unmeasured. Deliver the lane-C0 table + go/no-go.
- **Gate**, then **T2** (conditional, separately planned): port the nc_service transport
  substrate and run the pod-to-pod bandwidth check to measure the **one UNMEASURED item =
  real net1 wire** — even nc_service only has loopback; real net1 is PENDING there too.

## Implications / next actions

- [ ] Session prompts already written: `docs/session-prompts/M2-E11.md` (T1→T2),
      `docs/session-prompts/M2-E13.md`. E13 (decode→host egress) runs fully parallel to E11.
- [ ] Register's E11 row still says "free same-fixture comparison" — reword to
      "cross-card-aware, T1 synthesis / T2 gated port" when maintaining.

## Pointers

- Related premise now settled: [[a7-Lp-vs-Lg-settled-on-tracelab]] (the `L_g ≫ L_p` claim
  came from the mtbench8 validation fixture, not real serving).
- nc_service PD trace: [[../../../nc_service/memory/topics/specdec-modeb-pd-module-trace]].
