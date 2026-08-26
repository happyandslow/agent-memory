# O1 promoted to formal M1b decode continuous-batching milestone — 2026-08-25

**Project:** WaferEngine-staging
**Author:** codex
**Status:** captured

## What happened / finding

- When a cross-cutting continuous-batching roadmap needs formal tracking without
  renumbering the existing M2--M6 milestones, use **M1b · Decode continuous
  batching** and retain O1 only as its historical research/register alias.
- M1b and M1-S4 overlap; neither whole milestone is the prerequisite of the
  other. **M1b-S0/D0 and M1b-S1/D1** are the shared independent-position and
  per-lane-completion substrate. **M1b-S5/K0** integrates that substrate with
  fixed-slot KV reuse and is the joint gate that closes M1-S4.
- **M1b-S2/D2a, S3/D2b, and S4/D2c** add cross-round continuation,
  completed-lane removal, and boundary admission/replacement. They precede K0
  in the approved branch stack but are not ragged-execution acceptance
  requirements.
- `K0` is only the earlier roadmap alias for formal stage **M1b-S5**, the first
  KV-integration stage after the main-based D0--D2c stack. It is not an existing
  kernel, protocol object, branch, or earlier M1 subtask. First references
  should use `M1b-S5/K0`.
- M1b is decode-only. PF/full continuous prefill, completion-triggered early
  close, asynchronous transport, communication compaction, and on-device
  scheduling remain later separately reviewed work.

## Implications / next actions

- [ ] Review M1b-S0/D0's exact metadata, heterogeneous-prefix ingress, RoPE
      representation, gates, and branch base before any implementation.
- [ ] Keep M1-S3 cleanup as an M1b-S5/K0 closure prerequisite, not a blocker to
      neutral main-based M1b-S0-S4 work.
- [ ] Do not create a branch or mark any M1b checkbox from milestone scheduling
      alone; every stage still requires separate review and approval.

## Pointers

- Formal milestone: `milestones/M1b-decode-continuous-batching.md`
- Updated M1 gate: `milestones/M1-intra-pe-reuse.md`
- English audit: `docs/analysis/2026-08-24-o1-continuous-batching-roadmap.md`
- Chinese translation: `docs/analysis/2026-08-24-o1-continuous-batching-roadmap.zh-CN.md`
- Tradeoff register: `milestones/kv-reuse-tradeoff-register.md`
