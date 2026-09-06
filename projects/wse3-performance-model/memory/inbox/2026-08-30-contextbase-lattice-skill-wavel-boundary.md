# ContextBase Lattice-Skill/Wavel boundary — 2026-08-30

**Project:** wse3-performance-model
**Author:** codex
**Status:** captured   <!-- captured | drained -->

## What happened / finding

- When the Wavel author's "lattice search" wording appears without a source
  pointer, ContextBase search resolves `Lattice-Skill` as a separate
  cross-operator tile-flow planning project, not as a class, plugin, branch, or
  verified capability in the current Wavel repository.
- Its design borrows Wavel's information-compression boundary: search a compact
  mapping strategy, then derive communication and executable mapping from
  hardware/backend rules. It explicitly does not inherit Wavel PE rectangles,
  a particular CUT/TUNE action vocabulary, or a GPU-completeness claim.
- Lattice-Skill currently calls its mathematical object a typed rewrite graph
  and says strict lattice semantics require separate proofs of order, closure,
  and meet/join. This ContextBase planning evidence therefore does not upgrade
  clean Wavel `main@9b5e88b` beyond the source-audited A* state graph.
- The useful architectural analogy is: S4 CandidatePlan ~= compact
  StrategyPlan; S2 hardware/provider contracts feed evaluation; future KAIR
  closure/materialization ~= intelligent completion. The analogy is not an
  existing Wavel-to-KAIR adapter.

## Implications / next actions

- [ ] Keep current Wavel lattice capability classified unknown until the author
  supplies an exact branch, commit, API, or implementation pointer.
- [ ] Use Lattice-Skill only as design input for S2-S4 boundaries; retain
  source-backed WSE differences such as explicit movement-witness selection.

## Pointers

- https://context.ed-aisys.com/doc/project-overview-GbvVr8BvRs
- https://context.ed-aisys.com/doc/research-note-03-strategyplan-and-intelligent-completion-D3KXqHrpOA
- https://context.ed-aisys.com/doc/transform-algebra-search-and-optimality-6vKvntRtM0
- https://context.ed-aisys.com/doc/risks-decisions-and-research-queue-WbI9W1P8Ef
- `/home/lexu/wse3-performance-model/docs/analysis/2026-08-27-wavel-capability-audit.md`
