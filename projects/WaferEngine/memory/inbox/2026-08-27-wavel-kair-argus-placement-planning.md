# Wavel + KAIR + Argus for WaferEngine placement planning — 2026-08-27

**Project:** WaferEngine
**Author:** codex
**Status:** captured

## Situation / finding

- Situation: WaferEngine can measure a small number of hand-built decode/prefill
  layouts, but implementing each new PE placement takes too long. The immediate goal
  is therefore not arbitrary CSL synthesis. It is to make placement alternatives
  cheap to describe and compare, using an implementation-sensitive performance model
  and Wavel's A* mapper while accounting for the constraints that make a candidate
  realizable.
- The motivating SRAM problem is code/control replication: current large synchronous
  blocks carry most or all layer logic on every compute PE. The inspected Qwen3-4B
  snapshot demonstrates a role split in which each physical block row owns one layer
  slice but uses separate compile-time-specialized ATTN and FFN regions connected by
  static multicast; ATTN owns KV ingress/cache and FFN does not.
- Decision from Le: start with the simpler **planning-only** slice. First make the
  performance model pluggable, predict ATTN/FFN regions at different sizes/shapes (or
  decompose them into GEMM/GEMV and other primitives), add explicit communication-
  algorithm predictions between units, and use A* to choose placements subject to
  constraints. Defer general kernel/state-machine synthesis.

## Relationship among the three projects

- **Wavel** is the outer graph grouping/mapping/search system. Its current A* search
  uses CUT/TUNE/PLACE/DUPLICATE/FIX over operation groups and rectangular PE regions.
  It already has WSE-oriented GEMM/GEMV/collective cost machinery and a bounded CSL
  backend, but its search state and SRAM model are not yet rich enough for the 4B
  role/state-machine placement problem.
- **KAIR** is the intended resource-time target IR and legality/certification layer,
  not merely another performance estimator. It can represent exact implementation
  witnesses as resource claims, ordering/protocol obligations, closure consequences,
  conflicts, and certificates. Its current repository does not yet contain a complete
  WSE profile or a Wavel adapter.
- **Argus** is the outer campaign/orchestration layer: it can invoke deterministic
  search, certification, generation, compile/simulator/device gates, review evidence,
  and resume experiments. It should not replace Wavel's combinatorial solver or
  KAIR's legality semantics.
- Recommended composition: Wavel explores candidate groupings/placements and explicit
  implementation witnesses; the chosen candidate lowers to KAIR target IR for WSE
  resource closure/certification and trace-based costing; a materializer later emits
  WaferEngine/SdkLayout artifacts; Argus orchestrates calibration and validation.
- Current-code fact: Wavel and KAIR are not integrated today. Author-stated future
  intent (received 2026-08-26) is: **“KAIR 的计划是未来成为 wavel 的 target IR，后续所有
  硬件都从 KAIR 接入进去，wavel 从 wafer-size 转变为通用的 mapper。”** Treat this as
  roadmap intent from the KAIR author, not as implemented behavior. Source screenshot:
  `projects/WaferEngine/assets/2026-08-27-kair-author-wavel-target-ir.png`.

## Proposed first placement-planning slice

1. Freeze a small candidate vocabulary. A prediction unit is either a coarse,
   versioned ATTN/FFN role bundle or a fine GEMM/GEMV/normalization/collective
   composition. Mixing is allowed only through an explicit lowering contract.
2. Introduce a pluggable performance-model interface. Each compute prediction takes
   operation/bundle identity, tensor shape, PE rectangle, dtype, implementation
   witness, and calibration identity; it returns latency or phase trace, SRAM claims,
   uncertainty, and evidence grade rather than one context-free scalar.
3. Represent every communication edge with an **algorithm witness**, not just byte
   count and distance: e.g. static row multicast A/B, reconfigured tree all-reduce,
   store-and-forward return, K-pipe/strip transport, or point-to-point shift. The
   witness carries route geometry, payload, colors, IQ/OQ, repaint/drain/fence rules,
   and a versioned cost function.
4. Extend A* state from `(operations, rectangle)` to include role/bundle identity,
   implementation witness, layer slice, orientation, persistent ownership, and
   communication witness. Prune candidates through exact/declared constraints before
   accepting their predicted cost.
5. Replay known layouts before searching novel ones: the current 4B 2x4 role split,
   a capacity-negative or slower control, and one bounded alternative. The first
   success criterion is correct ordering and an honest SRAM/throughput frontier, not
   a universal low percentage error.

## Missing steps / blockers

- **Search representation:** Wavel GroupState lacks role images, layer ownership,
  persistent state, implementation/communication witnesses, code residency, and
  protocol state.
- **SRAM admission:** Wavel currently models parameters, activations, and 10% workspace
  but not `.text`, KV, scratch/arena, task table, runtime/system sections, alignment,
  or final-link occupied union. This is fatal for the code-dominated placement goal.
- **Communication fidelity:** existing formulas primarily use shape, span, payload,
  and distance. They do not yet guarantee that the priced route/queue/repaint/backpressure
  behavior is the behavior a generated or frozen implementation executes.
- **Fine resources and legality:** colors, separate IQ/OQ banks, physical links/ramps,
  route lifetime, queue binding/rebind, task IDs, DSR/DSD state, drains/fences, STOP
  propagation, and host I/O need a WSE profile and KAIR lowering.
- **Schedule semantics:** Wavel MeshSchedule currently has COMPUTE/RESIZE/MOVE over PE
  rectangles. It does not represent long-lived role loops, headers, KV ingress,
  barriers, re-arm, EOS/STOP, or offload/fetch; CSL RESIZE is also not generated.
- **Materialization:** current CSL output is one `wavel_pe.csl` over one rectangle.
  WaferEngine 4B uses multiple SdkLayout code regions and support roles. A later
  generator must specialize and connect frozen role implementations before attempting
  arbitrary leaf arithmetic or state-machine synthesis.
- **Calibration/provenance:** every cost must be keyed by witness version, target,
  parameters, calibration set, and evidence grade. Analytical, simulator, and device
  numbers must remain distinct; use uncertainty where ranking could change.
- **Integration:** Wavel→KAIR target-IR lowering and Argus tool/campaign adapters do not
  exist yet.

## Near-term acceptance criteria

- A plugin can predict the same compute unit at multiple PE shapes without changing
  Wavel's A* implementation.
- Communication choices are explicit candidates with algorithm-specific costs and
  resource claims; the search cannot price one witness and later materialize another.
- The known 4B baseline imports as a legal candidate with its ATTN/FFN ownership and
  communication edges intact.
- Seeded illegal SRAM, color/queue, geometry, and drain/rebind candidates fail closed.
- A* produces a Pareto or clearly scalarized ranking over performance, SRAM headroom,
  and PE footprint, with uncertainty/evidence labels.
- Kernel generation remains out of scope for this first slice; the handoff contract to
  later materialization is nevertheless explicit and versioned.

## Pointers

- `/home/lexu/KAIR/.trellis/tasks/08-26-inspect-wavel-kair-argus/{prd,design,implement}.md`
- `/home/lexu/KAIR/Argus/wavel/src/wavel/mapping/mapper.py`
- `/home/lexu/KAIR/Argus/wavel/src/wavel/mapping/knobs_cost.py`
- `/home/lexu/KAIR/Argus/wavel/src/wavel/mapping/memory.py`
- `/home/lexu/KAIR/Argus/wavel/src/wavel/backends/csl/`
- `/home/lexu/worktrees/1.7b-pipeline-af@93a6d0e/models/qwen3_4b-decode/`
- `projects/WaferEngine/memory/topics/pe-sram-memory-breakdown.md`

