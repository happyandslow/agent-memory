# MeshJIT P=256 pointer-alias fmaxh producer isolated — 2026-08-24

**Project:** WaferEngine
**Author:** codex
**Status:** captured

## What happened / finding

- Situation: P=256 Attention max-only returned `15.015625` on all 65,536 PEs instead of the true `19.90625`; prior phase tracing showed the fabric tree was coherently reducing each PE's local lane 15.
- A real-CS-3 three-arm experiment used fresh runtimes, deterministic identical f16 inputs, the byte-identical legacy `validation_diag_max_host`, and an unchanged `comm_pe.csl` / `all_reduceMax_bsz` (`e56d46853c4228ba23f05d840ed764c95001a432ad1ae11091aadf16f898b1cc`).
- The legacy pointer-alias producer `@fmaxh(ptr_max, max, src_dsr)` preserved the failure: 65,536 post-collective mismatches, uniformly `15.015625`.
- An explicit `@map` loop-carried accumulator and a sequential scalar-loop producer each had zero raw-f16 mismatches against every PE's local 16-lane maximum before the collective, then zero mismatches against the wafer maximum after the unchanged collective.
- The unchanged shifted positive control also had zero global-max and shifted-score mismatches. All four score tensors had raw-f16 SHA-256 `498ffa9f9fa701b9f01c89eabaf32a642e0562c8ce0e8f9f5fe38bf447216420`.
- Verified conclusion: the failure is in the original PE-local pointer-alias `@fmaxh` reduction construction, not route repaint, collective phase 1/2, broadcast, stale packets, or passive late visibility. This device result isolates behavior; it does not claim the undocumented compiler/CE implementation mechanism.

## Implications / next actions

- [ ] Replace the pointer-alias producer with the explicit `@map` accumulator in both validation baseline and Attention page sources.
- [ ] Regenerate fixed-address page/catalog/receiver artifacts and rerun the full P=256 baseline-versus-dynamic shared-slot raw-f16 comparison.
- [ ] Check NaN and signed-zero semantics before treating the comparison-based callback as a production-wide replacement for `fmaxh`.

## Pointers

- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-runtime-validation/full-baseline-local-max-three-arm/REPORT.md`
- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-runtime-validation/full-baseline-local-max-three-arm/device_results.json`
- Artifact SHA-256: `e568ec86670431aaa5ad5fa2471e7c6baccee39e1067593b7bbb2ed241496224`
- Source-tree SHA-256: `de12a0a07b6c09c92ead87572efd490fbfe00e3690c64fd73c8baf0e8aa20ddd`
- `projects/WaferEngine/memory/inbox/2026-08-24-meshjit-p256-max-reduce-last-lane-input.md`
- `https://context.ed-aisys.com/doc/2026-08-24-session-p256-shared-slot-validation-and-max-reduction-localization-OYpotFI2Ld`
