# Wavel placement-aware communication templates — 2026-09-01

**Project:** wse3-performance-model  
**Author:** codex  
**Status:** captured

## Situation

When Wavel evaluates U1 Qwen pipeline placement or U2 SRAM-offload placement,
payload bytes and Manhattan distance do not identify the implementation. The
same logical transfer may use a block-local collective, snake handoff, strip
relay, switch demux, GO-chain, or cascade, and placement geometry determines
which protocols are materializable and what they cost.

## Verified finding and decision

- Current Wavel CSL codegen has several distinct collective generators, but the
  mapper does not expose the U1/U2 protocol choice as a placement-search
  dimension. Generic `MOVE`/`RESIZE` costing remains largely
  bytes/distance/hops based, and the bounded `MOVE_KERNEL` only emits an
  eastward translation. Predictor algorithm labels are not a substitute for
  exact codegen/template identity.
- Le corrected the contract direction: every performance-relevant
  communication algorithm is a backend-qualified `ImplementationTemplate`,
  with placement applicability, source/destination layouts, relative topology,
  payload/phase boundary, generator identity, and local resource claims. An
  `ImplementationVariant` binds the exact relative geometry and payload;
  `CandidatePlan` owns absolute compute/storage placement and KAIR retains exact
  global closure authority.
- This applies to both use cases. U1 must map block-local collectives,
  inter-block handoffs, HT-head/tail paths, KV ingress, and other as-built edges
  to exact/partial/missing templates. U2 must keep v3 single-row, v4 GO-chain,
  and v5 cascade (plus owner-receive modes) as distinct protocol identities,
  then determine which real attention/storage placements each supports.
- Benchmark matrices are downstream of the communication-template audit. A
  matrix point is an exact template plus source/destination placement relation,
  layout, payload, phase, target environment, and protocol parameters—not just
  bytes and distance.
- Placement is not row-specific. The shared contract must describe general PE
  regions (for example rectangles, rows, columns, or explicit PE sets), while
  each communication template derives its own path, interface, fanout, and hop
  relation and rejects geometries that its generator cannot materialize. A
  centroid or Manhattan distance alone is not a sufficient implementation
  identity.
- The first storage-placement question is: given a fixed attention-block
  placement, enumerate storage placements, filter matching communication
  templates, predict exact variants, retain local resource claims/unknowns, and
  send candidates to KAIR closure. Interference remains explicitly unknown in
  the first blocking/non-overlapping model; overlapping candidates require
  later fused/concurrent evidence.
- The same exact-template prediction path serves two callers: Wavel can query
  alternatives during search, while an analysis frontend can bind a user-supplied
  hypothetical placement and return named compute/communication predictions for
  every covered element. Bundle decomposition and scheduling remain caller-owned;
  provider coverage boundaries prevent endpoint receive work or fused components
  from being counted twice.
- A separate ContextBase duplicate-pattern study provides a useful, bounded
  taxonomy: 14 mappings reduce to resident, nearest-replica, tiled-comb,
  periodic-stripe, single-axis-collective, and two-stage-collective families,
  crossed with `reload_always`, `selector_reuse`, and `catalog_cache` temporal
  policies. Its compiled artifacts also refute using replica count or duplicate
  payload bytes as total SRAM: receiver slots, staging, routing, code, and
  protocol state can make sparse placement consume more aggregate and peak SRAM.
  This is planning input only: the workload is a 20x20 hybrid tiny Transformer
  with fixed-ABI leaf functions, and its preregistered host-E2E drift gate failed,
  so it supplies neither an actionable placement recommendation nor U1/U2 model
  coefficients.
- Historical U2 results remain locator/regression references only. They do not
  populate the new profiles, transfer coefficients, or make mismatched timing
  boundaries comparable; M2 must measure the S3-frozen exact
  placement/template variants anew.

## Consequence

The S3 ordering gains a communication-template and placement-applicability
audit before finite matrix selection and benchmark requirements. Merely
freezing the Qwen source/config is insufficient. The checked-in Qwen3-4B device
config pair is not yet newly CS-3 validated and must not be recorded as such.

## Evidence pointers

- `/home/lexu/KAIR/Argus/wavel/src/wavel/backends/csl/kernels.py:2728`
- `/home/lexu/KAIR/Argus/wavel/src/wavel/backends/csl/kernels.py:6881`
- `/home/lexu/KAIR/Argus/wavel/src/wavel/mapping/mapper.py:891`
- `/home/lexu/KAIR/Argus/wavel/src/wavel/predictor/knobs/formulas.py:276`
- `/home/lexu/worktrees/1.7b-pipeline-af/models/qwen3_4b-decode/src/comm_lib/comm_pe.csl:676`
- `WaferEngine-staging@255dab72:models/qwen3_1p7b-decode/bench/m3_park_band/column_cycle_demo_multirow_v4/README.md:1`
- `WaferEngine-staging@255dab72:models/qwen3_1p7b-decode/bench/m3_park_band/column_cycle_demo_multirow_v5/README.md:1`
- ContextBase planning analogies (not Wavel capability evidence): `2026-08-04
  Result: MeshJIT physical multicast cost + real c512 use time` and `[Experiment]
  Dissecting the chunks in WaferLLM Prefill`.
- ContextBase bounded placement taxonomy: `duplicate-pattern — Full experiment
  report` / `duplicate-pattern — Interactive HTML report` (Hybrid Serve,
  duplicate-pattern-v3).
