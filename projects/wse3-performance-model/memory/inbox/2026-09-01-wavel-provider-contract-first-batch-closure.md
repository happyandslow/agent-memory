# Wavel provider-contract first-batch closure — 2026-09-01

**Project:** wse3-performance-model  
**Author:** codex  
**Status:** captured

## Situation

When a Wavel performance model prices an implementation that will later be
materialized, source revision alone is either too weak (if treated as a loose
locator) or too invalidation-prone (if every comment-only commit creates a new
model identity). The S2 contract also needs to stay fail-closed without adding
runtime classes for every planning artifact.

## Confirmed decisions

- Pricing and materialization must resolve the same semantic
  `ImplementationTemplate` revision and exact `ImplementationVariant`.
  Generator selection is a structured nested `generator_entry`, not a peer
  materializer class; the contract term is "matching template generator for
  the exact implementation variant."
- Exact Git revision records source provenance. A semantic template revision
  controls model/cache compatibility. A new source revision may retain the
  semantic revision only after M2 conformance proves unchanged generator
  selection, emitted implementation, coverage, resource contract, target
  environment, and relevant template dependencies; otherwise it requires a new
  revision and model validation.
- Partial or missing generator coverage remains visible in the catalog but
  fails authoritative pricing with `NO_BOUNDED_MATERIALIZATION`.
- Required resource claims use a common-minimum-plus-family-extensions policy.
  Every template declares the common PE/code/scratch/communication-buffer/
  lifetime/interference records plus applicable compute, communication,
  role/event-driven, or storage/offload extensions. An applicable record may
  be explicitly unknown, but cannot be omitted or converted to zero; KAIR
  retains target-wide sufficiency authority.
- Hierarchical templates use `materialization_mode: direct | composed`.
  Direct templates require one bounded generator; composed templates require
  exact child variants and deterministic bindings. The first U1 evidence/model
  stage is coarse-first for one fixed model/input shape: attention and FFN
  templates vary rectangular PE-region size and placement while their internal
  implementation closure stays fixed. Model dimensions such as hidden/head
  sizes and head counts are baseline identity, not first-stage query axes.
  Internal collectives remain within each coarse component; inter-component
  communication is an independently predicted edge. Attention and FFN are
  measured separately, with a complete layer retained only as a sanity check.
  The initial coarse templates must be extracted from the frozen canonical
  Qwen implementation and retain its exact child/generator closure; logical
  reimplementations are not interchangeable evidence.
- `PERegion` v1 is one axis-aligned rectangle; multi-shard or irregular
  placements are lists of rectangle refs. Exact region objects and the derived
  producer/consumer geometry relation (offset, orientation, adjacency, facing
  boundary, and centroid delta) stay separate so communication models do not
  collapse placement to one distance.
- Before Wavel adoption, a handwritten-plan harness must exercise the neutral
  SDK plus the normal M2 registry/query/resource-claim path. It preserves exact
  identities and structured unknown/failure behavior, performs no search, and
  does not claim KAIR legality. The same plan later serves as an equivalence
  oracle for Wavel-generated query objects.
- Bounded extrapolation remains a provider-result property. S4 owns an
  explicit `allow_bounded_extrapolation` switch that defaults to false;
  provider queries remain ranking-policy-independent.
- Coarse and child prediction coverage is exclusive: a coarse full-transaction
  prediction is never added to predictions for children it already covers.
- Closure scheduling belongs to S4/S5. S2 fixes only the identity-preserving,
  explicit-unknown handoff to authoritative KAIR closure.
- Canonical JSON bytes and complete synthetic U1/U2 object bundles provide the
  deterministic S2 fixture gate. S3 baseline/benchmark manifests use a
  design-time conformance schema that references S2 identities but is not a
  runtime provider-contract class.
- Tracking uses a schema-complete checkpoint after S2 decisions and synthetic
  fixtures, while final S2 completion waits for identity-preserving round trips
  of the real S3 baseline/benchmark manifests.

## Confirmed second-batch refinements

- `ImplementationTemplate.generator_entry` is a nested tagged union covering
  compute-kernel registries, collective-template registries, schedule-event
  generators, and external template files; these forms do not become peer
  public classes.
- A template records exact direct template dependencies plus a canonical
  transitive dependency root. Generator helper functions/files remain source
  dependencies under exact Git provenance rather than becoming templates.
  Models and caches bind the top-level immutable template identity, which
  includes that dependency root.
- Bound parameter changes create a new `ImplementationVariant`; changes within
  one algorithm/protocol family that can affect emitted code, resources, or
  performance create a new template revision; independently selectable
  algorithms, protocols, communication schedules, data layouts, or coverage
  boundaries create distinct template IDs. Comment/format-only source changes
  may retain a semantic revision only after conformance.
- The first catalog audit is use-case-first: cover U1 Qwen decode/prefill and U2
  v3/v4/v5 offload requirements plus their transitive template dependencies,
  rather than inventorying all Wavel generators.
- Materialization coverage (`exact`, `partial`, `missing`, or
  `not_applicable`) is separate from verification level (`source_resolved`,
  `materialization_conformant`, or `device_validated`). Source inspection alone
  never claims runtime validation.
- A new Git source revision may reuse an existing model only when conformance
  preserves the semantic template manifest, dependency root, selection
  behavior, normalized emitted implementation, coverage, resource signature,
  and target environment; otherwise a new template revision and model
  validation are required.

## Boundary

The U1 canonical source/config choice is recorded separately in
`2026-09-01-qwen3-4b-config-device-validation.md`. Exact U1/U2 template
benchmark matrices, correctness/repetition requirements, and M2 evidence remain
outside this capture and must not be inferred from these contract decisions.

## 2026-09-01 closure-audit refinement

- The older S2 TODO list mixed true contract blockers with resolved or
  downstream work. Four S2 gates remain: normative nested generator/source/
  dependency metadata; concrete deterministic U1/U2 bundles; the S3
  manifest-conformance envelope plus real manifest round-trips; and the final
  normative-field/control audit.
- Extrapolation opt-in, coarse coverage exclusivity, generic-concurrency
  deferral, closure-scheduling ownership, and the canonical Qwen3-4B
  source/config selection are already decided or explicitly outside S2.
- Before Wavel adoption, U1/U2 experiment manifests and M2 providers must be
  exercised by a neutral handwritten-plan path. The deployment discussion is
  recorded in the project plan artifact rather than duplicated here.

## 2026-09-01 schema-complete refinement

- S2 is schema-complete after freezing canonical serialization/self-digest
  rules, nested generator/source/dependency identity, concrete synthetic U1/U2
  bundles with all three provider states, the design-time S3 manifest envelope,
  and the final normative-field/control audit. No S2 material contract decision
  remains open.
- S2 overall remains open behind one external-input gate: the real Qwen3-4B,
  Qwen3-1.7B, and SRAM-offload S3 baseline/benchmark manifests must preserve
  their exact S2 identities through the frozen envelope. Real witnesses,
  calibration, and models remain M2 work.
- The separate S3 discussion prompt is explicitly an information-maximizing
  experiment-axis/matrix-selection task. A handwritten plan only identifies
  one exact experiment row; the prompt does not design the predictor, Wavel
  search, CandidatePlan, or KAIR closure.
