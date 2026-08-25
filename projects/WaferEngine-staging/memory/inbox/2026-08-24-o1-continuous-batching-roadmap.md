# O1 continuous-batching staged roadmap — 2026-08-24

**Project:** WaferEngine-staging  
**Author:** codex  
**Status:** superseded by the approved 2026-08-25 decision below

## What happened / finding

- A design-only source audit separated ragged execution from continuous batching:
  M1-S4 must first establish per-lane position, RoPE, score addressing, and
  actual-EOS-length correctness under static membership. Dynamic admission also
  needs an iteration transaction, request/lane/slot ownership, input-source
  selection, output attribution, and rollback semantics.
- The recommended first O1 implementation slice is **synchronous token-epoch
  admission/replacement** after M1-S4. At the global epoch after a lane EOSes,
  host commits/releases that lane and binds a queued request while other lanes
  keep progress. It intentionally retains fixed compiled `bsz`, fixed
  communication/output extent, and a global barrier; it is a semantics gate,
  not a throughput claim.
- Current C1-M's real-device negative result remains mechanism-specific:
  fixed-communication local predicate skipping does not prove or disprove C2,
  EOS masking, compaction, or continuous batching.
- The code has five separate boundaries that could be meant by “same KV policy
  in a batch”: reuse facts, caller eligibility, allocation/LRU, residency
  mechanism, and cross-tier policy. Do not silently choose one.

## Implications / next actions

- [ ] Le reviews the M1-S4/CB-P0 state and verification contract.
- [ ] Le decides policy meaning, lane input-source contract, EOS release timing,
      and epoch/retry identity before CB-1 implementation.
- [ ] Do not create an O1 implementation branch before that review.

## Pointers

- In-repo English design: `docs/analysis/2026-08-24-o1-continuous-batching-roadmap.md`
- In-repo Chinese translation: `docs/analysis/2026-08-24-o1-continuous-batching-roadmap.zh-CN.md`
- ContextBase: <https://context.ed-aisys.com/doc/2026-08-25-decision-o1-main-first-continuous-batching-roadmap-T8ZrZvjYEi>
- Superseding capture: `memory/inbox/2026-08-25-o1-main-first-continuous-batching-decision.md`
