# Wavel template/model identity gap — 2026-08-31

**Project:** wse3-performance-model  
**Author:** codex  
**Status:** captured

## Verified finding

- Wavel's CSL materializer dispatches compute events to concrete `Kernel` generators, including distinct Cannon and SUMMA bodies for the same `matmul`/`gemm` operation type. The selected body depends on an explicit algorithm attribute or the program rectangle.
- The current mapping cost path dispatches by `op_type`; its GEMM call does not carry the code generator's selected algorithm and the predictor defaults generic `gemm` to `meshgemm`. Consequently, a `matmul` priced with one implementation model can be materialized by another body—for example, a SUMMA-priced instance could be emitted as Cannon if their template identities are not preserved.
- Wavel also has six concrete `CollectiveTemplate` identities and one bounded east-only `MOVE_KERNEL`; predictor aliases and IR operation names cover a broader set and are not proof of CSL materializability.
- Le confirmed the governing decision: performance models are defined directly over backend-qualified, versioned implementation-template instances, and the same template identity must survive modeling, query/result handling, CandidatePlan selection, and materialization. Two templates may implement the same logical operation yet require different model and cache identities; `op_type`, shape, or a loose source reference alone is insufficient. Template granularity may be atomic, fused, or role-level, but any hierarchy/composition must remain explicit and must not double-count a fused model with its children.
- Le confirmed the resource-authority split: a template catalog or claim resolver may return versioned template-local code/state/scratch/buffer/protocol claims (`known`, `upper_bound`, or `unknown`), and Wavel may use them only for conservative necessary-condition pruning. Neither M2 nor Wavel may return target-wide `feasible=true`; KAIR closure remains authoritative for resource sufficiency, coexistence, exact colors/queues/tasks/routes/buffers/lifetimes, and final legality.
- Le chose the public identity vocabulary `TargetHardware`, `TargetEnvironment`, and `ImplementationTemplate`. Generator selection/body metadata is embedded in `ImplementationTemplate` rather than exposed as a peer `CodegenEntry` identity: selecting the template already fixes the generator, while candidate-specific bound parameters remain a separate implementation-variant identity. `TargetEnvironment` describes the SDK/ABI and closure-schema environment; operator placement/PE geometry belongs to the candidate or implementation variant, not the target topology.
- Le confirmed the public model vocabulary and cardinality: an `ImplementationTemplate` has many bound `ImplementationVariant`s; immutable `ImplementationWitness` result groups observe exact variants; a `ModelCalibration` selects multiple compatible witnesses and reproducibly produces one model artifact; and a `PerformanceModel` is the versioned prediction function with embedded applicability and metric boundary. A performance query selects one exact variant and one compatible model, not an individual witness. Variant configuration such as concurrency is an input dimension; one model may cover isolated and concurrent values when its applicability and calibration evidence support them. Separate models are required only when target environment, metric boundary, model artifact/evidence set, applicability, or version differs—not merely because one input parameter has different values.
- Le selected a deliberately simple runtime mapping: once Wavel has fixed an exact `ImplementationVariant`, `PerformanceQuery` names the exact active canonical `PerformanceModel` and provider directly. Model/provider selection is not a Wavel planning knob and does not require a two-stage runtime resolution object. Historical model/provider versions may remain for reproducibility, but the active registry mapping for one template revision, target environment, and metric is unique.
- Le confirmed that S2 must retain explicit extrapolation semantics rather than imposing a contract-wide rejection rule. A model must distinguish calibration-domain use, bounded extrapolation, and out-of-domain failure; the exact bounded-domain and uncertainty/ranking policy remains to be settled rather than silently inferred.

## Implications / next actions

- [ ] Audit the use-case-required atomic and fused templates before deciding which profiles to populate.
- [ ] Map the existing Qwen decode/prefill role pipeline and the v3/v4/v5 storage-offload implementations onto the template catalog, marking exact, partial, and missing coverage; use the gaps to define template-completion work and the covered set to select required performance tests.
- [ ] Require query/result/cache identity to change when the selected template body, selection-relevant attributes, backend, target environment, performance model, SDK, or template composition changes.
- [ ] Preserve the transitive witness set through `ModelCalibration` and `PerformanceModel` provenance without adding witness selection to each performance query.
- [ ] Keep predictor-only support distinct from materializer support; fail closed when no matching bounded template exists.
- [ ] Name the local interface `TemplateResourceClaimQuery` / `TemplateResourceClaimSet` (or equivalent) rather than a feasibility/admission provider, and preserve every unknown through the Wavel-to-KAIR handoff.

## Evidence pointers

- `/home/lexu/KAIR/Argus/wavel/src/wavel/backends/csl/kernels.py:6571-6822`
- `/home/lexu/KAIR/Argus/wavel/src/wavel/backends/csl/kernels.py:1768-1900`
- `/home/lexu/KAIR/Argus/wavel/src/wavel/backends/csl/kernels.py:2728-2868`
- `/home/lexu/KAIR/Argus/wavel/src/wavel/backends/csl/kernels.py:6880-7136`
- `/home/lexu/KAIR/Argus/wavel/src/wavel/backends/csl/program.py:382-419`
- `/home/lexu/KAIR/Argus/wavel/src/wavel/mapping/cost.py:53-82`
- `/home/lexu/KAIR/Argus/wavel/src/wavel/mapping/cost.py:145-175`
- `/home/lexu/KAIR/Argus/wavel/src/wavel/predictor/api.py:147-152`
