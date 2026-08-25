# O1 main-first decode continuous-batching roadmap approved — 2026-08-25

**Project:** WaferEngine-staging  
**Author:** codex  
**Status:** captured

## What happened / finding

- Le approved the roadmap order **D0 -> D1 -> D2 -> K0 -> PF**. Approval is
  for the decomposition only; it does not authorize an implementation branch,
  production-code changes, simulator runs, CS-3 runs, staging, or commits.
- **D0, D1, and D2 are all based on `origin/main` at `S=M`.** D0 adds
  lane-local position/score/RoPE execution and D1 adds lane-local EOS and
  actual progress with no write after EOS. D2 reuses the existing host-visible
  decode-budget round/re-arm seam as controller quantum (`Q=decode_budget`):
  D2a preserves requests across rounds, D2b removes completed lanes at a
  boundary, and D2c admits queued replacements there. D2 is the minimum useful
  continuous-batching semantic slice only after D2c.
- D2a must prove round-segmentation invariance under identical sampling inputs:
  uninterrupted execution and multiple `Q` values produce the same token
  stream, KV, positions, EOS point, next-token/RoPE continuation, and sampling
  RNG seed/counter progression. `Q=1` is the degenerate fine-grained host
  controller configuration, not a performance prescription.
- **K0 starts only after reviewed D2.** It semantically ports or deliberately
  replays `kv-feature@77d6d407` fixed-slot behavior onto D0-D2: `S>=M`,
  `active_slot[]`, reuse planning, owner/`valid_len`/ledger state, and
  success-only commit. A mechanical rebase is not assumed because the source
  lines overlap heavily.
- D0/D1 provide the M1-S4 ragged-execution acceptance substrate, but M1-S4
  remains open until K0 re-verifies it on the KV line. The remaining M1-S3
  ownership cleanup and post-cleanup inert/device gate block K0 closure, not
  main-based D0-D2.
- Completion-triggered early close, a persistent command stream, async
  ingress/egress, communication compaction, dynamic physical extent, and
  on-device scheduling are not required for D2 semantics. They remain later,
  measurement-gated mechanisms. New arrivals wait for the next `Q` boundary;
  scheduler replay must measure the boundary-overhead/admission-delay tradeoff
  as a function of `Q`. PF first defines admission of an externally produced
  prefill result; full prefill continuous batching is later.

## Implications / next actions

- [ ] Review D0's exact metadata, heterogeneous-prefix ingress representation,
      RoPE representation, and gates before creating its main-based branch.
- [ ] Repeat a separate plan/review/implementation/review cycle for D1, D2a,
      D2b, D2c, K0, and PF; implementation is performed by a subagent and
      independently reviewed by the planner/reviewer.
- [ ] Before K0, choose the semantic-port/replay method and define whether
      “same KV policy in a batch” means reuse facts, caller eligibility,
      allocation/LRU, residency mechanism, or cross-tier policy.
- [ ] Preserve C1-M only as a fixed-communication mechanism anchor; do not
      infer unmeasured continuous-batching performance.

## Pointers

- English roadmap: `docs/analysis/2026-08-24-o1-continuous-batching-roadmap.md`
- Direct Chinese translation: `docs/analysis/2026-08-24-o1-continuous-batching-roadmap.zh-CN.md`
- ContextBase: <https://context.ed-aisys.com/doc/2026-08-25-decision-o1-main-first-continuous-batching-roadmap-T8ZrZvjYEi>
