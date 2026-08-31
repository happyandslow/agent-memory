# Wavel template/profile identity gap — 2026-08-31

**Project:** wse3-performance-model  
**Author:** codex  
**Status:** captured

## Verified finding

- Wavel's CSL materializer dispatches compute events to concrete `Kernel` generators, including distinct Cannon and SUMMA bodies for the same `matmul`/`gemm` operation type. The selected body depends on an explicit algorithm attribute or the program rectangle.
- The current mapping cost path dispatches by `op_type`; its GEMM call does not carry the code generator's selected algorithm and the predictor defaults generic `gemm` to `meshgemm`. Consequently, a `matmul` priced with one implementation profile can be materialized by another body—for example, a SUMMA-priced instance could be emitted as Cannon if their template identities are not preserved.
- Wavel also has six concrete `CollectiveTemplate` identities and one bounded east-only `MOVE_KERNEL`; predictor aliases and IR operation names cover a broader set and are not proof of CSL materializability.
- Le confirmed the governing decision: performance models are defined directly over backend-qualified, versioned implementation-template instances, and the same template identity must survive profiling, query/result handling, CandidatePlan selection, and materialization. Two templates may implement the same logical operation yet require different model and cache identities; `op_type`, shape, or a loose source reference alone is insufficient. Template granularity may be atomic, fused, or role-level, but any hierarchy/composition must remain explicit and must not double-count a fused profile with its children.

## Implications / next actions

- [ ] Audit the use-case-required atomic and fused templates before deciding which profiles to populate.
- [ ] Map the existing Qwen decode/prefill role pipeline and the v3/v4/v5 storage-offload implementations onto the template catalog, marking exact, partial, and missing coverage; use the gaps to define template-completion work and the covered set to select required performance tests.
- [ ] Require query/result/cache identity to change when the selected template body, selection-relevant attributes, backend, target/profile, SDK, or template composition changes.
- [ ] Keep predictor-only support distinct from materializer support; fail closed when no matching bounded template exists.

## Evidence pointers

- `/home/lexu/KAIR/Argus/wavel/src/wavel/backends/csl/kernels.py:6571-6822`
- `/home/lexu/KAIR/Argus/wavel/src/wavel/backends/csl/kernels.py:1768-1900`
- `/home/lexu/KAIR/Argus/wavel/src/wavel/backends/csl/kernels.py:2728-2868`
- `/home/lexu/KAIR/Argus/wavel/src/wavel/backends/csl/kernels.py:6880-7136`
- `/home/lexu/KAIR/Argus/wavel/src/wavel/backends/csl/program.py:382-419`
- `/home/lexu/KAIR/Argus/wavel/src/wavel/mapping/cost.py:53-82`
- `/home/lexu/KAIR/Argus/wavel/src/wavel/mapping/cost.py:145-175`
- `/home/lexu/KAIR/Argus/wavel/src/wavel/predictor/api.py:147-152`
