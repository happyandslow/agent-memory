# MeshJIT P=256 Attention→FFN shared-slot E2E PASS — 2026-08-24

**Project:** WaferEngine
**Author:** codex
**Status:** captured

## What happened / finding

- Situation: after the P=256 shared-slot protocol passed but raw-f16 first diverged in Attention max and later FFN RMSNorm, the required gate was a fresh, config-frozen real-CS-3 baseline-versus-dynamic run covering catalog, slot lifecycle, all intermediate values, Final Z, closure, SRAM, and production immutability.
- Canonical run `p256-map-e2e-20260824-v5` used real geometry `P=256, bsz=1, dim/head_dim/seq_len=4096, ffn_dim=14336, layer_num=32`; correctness executes one Attention→FFN layer. It compared validation-only `B_U04_corrected` with `D_dynamic`, not the unchanged production baseline.
- The verified construction uses explicit loop-carried `@map` producers for Attention local max and FFN RMSNorm local sum. v3 showed `ffn_local_sum` was already bit-exact while `ffn_z_norm_tile` still differed by 1 ULP, excluding the local sum as the final cause.
- The remaining source-semantic difference was page `math.invsqrt(x)` versus baseline `1.0 / math.sqrt(x)`. v5 retains page `sqrt` and routes only division through fixed receiver wrapper `0x2c20`; Attention softmax and FFN SiLU use the same resident division service. No page-local `__divhf3` or unresolved relocation remains.
- Real CS-3 result: 19/19 checkpoints plus Final Z raw-f16/u16 bit-exact; mismatch count 0; Final Z SHA-256 on both sides `6cacce4edb688ae0772d03c165f6ae044046b06c5892e19dd9657680116e8dac`. Catalog/slot/state/phase-liveness gates passed and post-run `csctl get jobs` had no `congjiehe` jobs.
- Pages share `.m4_page@0x1a00`: Attention 4,080 raw B, FFN 2,148 raw B, each padded to 4,096 B. Catalog is 8,192 B with SHA-256 `50f07610d6953ecc6bb71fedf98372301efff41b5abf937db4453906e6d719dd`; holder readback is identical.
- Final-linked compute-PE capacity: corrected baseline 28,872 B allocated / 34,816 B high-water (26 specializations); dynamic receiver 32,054 B / 42,056 B (81 specializations), deltas +3,182 B / +7,240 B. High-water includes placement holes; this construction does not save receiver SRAM.
- Performance scope: these are SRAM/code-ownership/page/catalog economics only. No synchronized TSC/host-wall latency or throughput benchmark was run; cloud compile/job wall-clock is not performance data.
- Procedural promotion: the validated reproduction and first-divergence rules were added to the canonical `wse-shared-slot-artifact-validation` skill.

## Implications / next actions

- [ ] Treat `PASS_P256_MAP_MAX_SHARED_SLOT_E2E` as the correctness result only for this bsz1 Route-A/Policy-P/F4 construction and frozen source/config identities; use a fresh run ID and all fail-closed gates after any config, ABI, placement, policy, or source change.
- [ ] If performance is needed, design a separate synchronized device-TSC/host-wall experiment; do not reuse correctness run duration.
- [ ] Before proposing the comparison-based `@map` max as a production-wide change, independently audit NaN and signed-zero semantics.

## Pointers

- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-runtime-validation/p256-map-e2e/README.md`
- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-runtime-validation/p256-map-e2e/evidence/p256-map-e2e-20260824-v5/e2e_audit.json`
- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-runtime-validation/p256-map-e2e/evidence/p256-map-e2e-20260824-v5/device_compare_result.json`
- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-runtime-validation/p256-map-e2e/evidence/p256-map-e2e-20260824-v5/sram_audit.json`
- `/home/lexu/.codex/skills/wse-shared-slot-artifact-validation/references/waferllm-attention-ffn-p256.md`
- `projects/WaferEngine/memory/inbox/2026-08-24-meshjit-p256-pointer-alias-fmaxh-isolated.md`
- `https://context.ed-aisys.com/doc/2026-08-24-session-p256-shared-slot-validation-and-max-reduction-localization-OYpotFI2Ld`
