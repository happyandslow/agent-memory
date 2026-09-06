# Wavel/KAIR resource-legality boundary — 2026-08-30

**Project:** wse3-performance-model  
**Author:** codex  
**Status:** captured

## Verified finding

- At live KAIR revision `917ff95f57ea9c028c6c5a50448af7d631100f2c`, `close_plan` already owns authoritative closure outcomes: `Closed`, `NeedsRefinement`, `Conflict`, and `Rejected`.
- KAIR's registered capacity duty checks concrete compute, storage, bank, port, link, and queue claims against intervals, routes, queue occupancy, outer reservations, and the target profile. A non-`Closed` outcome cannot reach the WSE emitter.
- KAIR's fact-only partial analysis is not currently a capacity oracle: without plan claims and an outer reservation, the capacity rule intentionally emits no verdict.
- Therefore, a broad M2/Wavel `StorageFeasibilityResult` would overlap an existing KAIR authority. The S2 design should distinguish versioned performance/resource-demand claims and conservative Wavel pruning from authoritative KAIR closure. This boundary is a recommendation pending Le's confirmation, not a frozen contract decision.
- A tracked Wavel-to-KAIR adapter remains unavailable/unverified, so translating a complete Wavel candidate into KAIR `Plan<Candidate>` remains future design work.

## Implications / next actions

- [ ] Before freezing S2 names or ownership, discuss whether M2 returns resource-demand claims rather than an overall feasibility verdict.
- [ ] In later Wavel/adapter work, define conservative early pruning separately from complete-candidate KAIR closure; do not duplicate KAIR's exact legality rules.

## Evidence pointers

- `/home/lexu/KAIR/crates/kair-closure/src/lib.rs:1-22`
- `/home/lexu/KAIR/crates/kair-closure/src/close_plan.rs:176-225`
- `/home/lexu/KAIR/crates/kair-closure/src/rules/capacity.rs:1-23`
- `/home/lexu/KAIR/crates/kair-closure/src/rules/capacity.rs:117-125`
- `/home/lexu/KAIR/crates/kair-target-wse3/src/lib.rs:1-41`
- `/home/lexu/KAIR/crates/kair-target-wse3/src/reach.rs:12-77`
