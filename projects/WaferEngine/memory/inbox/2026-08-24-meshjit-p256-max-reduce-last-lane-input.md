# MeshJIT P=256 max-reduce consumes the last local lane — 2026-08-24

**Project:** WaferEngine
**Author:** codex
**Status:** captured

## What happened / finding

- Situation: the P=256 Attention max-only RPC reproducibly returns `15.015625` on all 65,536 PEs instead of the true global max `19.90625`; passive local delay does not repair it, while the same-artifact max-plus-dependent-subtract path is bit-exact.
- A real CS-3 phase-boundary artifact preserved both controls and duplicated `all_reduceMax_bsz` only for observation. The legacy max-only path remained uniformly wrong; legacy shifted had zero global-max and shifted-score raw-f16 mismatches.
- At the first-phase group-root boundary, 15 of 16 groups were wrong versus the true 16-lane PE-local maximum. Phase 2 and broadcast consistently propagated group 11's `15.015625`.
- Decisive structured identity: all 4,096 first-phase root observations exactly equal each group's max of `score[..., local_lane_15]` (zero raw-f16 mismatches), and the final 65,536 outputs exactly equal the wafer max of that lane (zero mismatches). The reduced value is `score[py=180, lane=15] = 15.015625`; the omitted true maximum is `score[py=231, lane=3] = 19.90625`.
- Therefore the two-phase fabric tree and broadcast are mathematically coherent for the inputs they actually receive. The first fault is upstream of the phase-1 fabric result: the PE-local `@fmaxh` reduction result lacks a proved completion/dependency handoff before `all_reduceMax_bsz` consumes it in the max-only path.
- This strongly weakens simple stale-packet/color-collision, phase-2, broadcast, and time-only late-visibility explanations. Route repaint can remain an interaction, but is not the leading direct mechanism because the wrong result is an exact last-lane reduction rather than arbitrary or cross-group data.
- Qualification: trace slots are SRAM-visible boundary samples, not transparent packet capture. The exact last-lane relation is verified from the same run's NPZ; the precise CSL/CE dependency mechanism remains unverified.

## Implications / next actions

- [ ] Add a minimal device-side dependency between the PE-local max destination and `all_reduceMax_bsz`, without changing the reduction arithmetic or fabric protocol.
- [ ] In the same artifact, retain unchanged legacy max-only and shifted controls; require max-only to change from the exact last-lane model to the true `19.90625`.
- [ ] If that passes, rerun the full P=256 baseline-versus-dynamic shared-slot raw-f16 comparison before claiming P=256 correctness.
- [ ] For future collective bugs, compare wrong outputs against individual local lanes before blaming routing; an exact lane-reduction identity distinguishes an upstream producer/completion fault from fabric corruption.

## Pointers

- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-runtime-validation/full-baseline-reduce-trace/cs3_evidence/2026-08-24/REPORT.md`
- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-runtime-validation/full-baseline-reduce-trace/cs3_evidence/2026-08-24/derived_analysis.json`
- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-runtime-validation/full-baseline-reduce-trace/cs3_evidence/2026-08-24/device_results.json`
- `projects/WaferEngine/memory/inbox/2026-08-24-meshjit-p256-max-reduce-passive-late-visibility-negative.md`
- `https://context.ed-aisys.com/doc/2026-08-24-session-p256-shared-slot-validation-and-max-reduction-localization-OYpotFI2Ld`
