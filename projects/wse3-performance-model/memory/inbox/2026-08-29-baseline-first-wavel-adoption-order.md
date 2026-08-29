# Baseline-first Wavel adoption order — 2026-08-29

**Project:** wse3-performance-model
**Author:** codex
**Status:** captured   <!-- captured | drained -->

## What happened / finding

- When adopting the Qwen3-4B role-placement and Qwen3-1.7B on-chip KV-offload
  use cases, the CandidatePlan test cannot depend on witness manifests frozen
  by a later task. Le approved renumbering the active plan so M1-S3 freezes
  both baseline witness families before M1-S4 CandidatePlan adoption.
- After S1b, S2 provider-contract design and S3 witness-manifest work may
  iterate in parallel; S4 begins only after both are stable. After M1, M2
  provider/model implementation and M3 baseline-import plumbing may also run
  in parallel, but calibrated ranking/search validation joins both paths.
- Both use cases use the same adoption loop: frozen WitnessSpecs -> provider
  query/import -> CandidatePlan baseline import -> baseline reproduction ->
  controlled variants -> thin Wavel-to-KAIR adapter -> bounded closure and
  materialization.
- Wavel owns search-visible PE-region allocation, full declared-resource
  admission, and registered protocol-witness selection. Future KAIR closure
  revalidates and binds exact global colors, queues, tasks, routes, buffers,
  and lifetimes without replacing the priced witness.
- A 2026-08-29 source/ref search found no literal lattice implementation, API,
  or mathematical meet/join semantics in clean Wavel `main@9b5e88b` or its
  advertised remote refs. The visible implementation is an A* state graph;
  the author's "lattice search" term remains unresolved pending an exact
  branch, commit, API, or design pointer.

## Implications / next actions

- [ ] Complete S1b, then join stable S2 and S3 outputs before starting S4.
- [ ] Ask the Wavel author for the exact lattice-search source boundary.

## Pointers

- `/home/lexu/wse3-performance-model/GOALS.md`
- `/home/lexu/wse3-performance-model/ROADMAP.md`
- `/home/lexu/wse3-performance-model/PROGRESS.md`
- `/home/lexu/wse3-performance-model/milestones/M1-wavel-pipeline-placement-plan.md`
- `/home/lexu/KAIR/Argus/wavel/src/wavel/mapping/state.py`
- `/home/lexu/KAIR/Argus/wavel/src/wavel/mapping/mapper.py`
