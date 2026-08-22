# Shared-slot artifact reaches CS-3 but baseline/page numerics diverge — 2026-08-22

**Project:** WaferEngine
**Author:** codex
**Status:** captured

## What happened / finding

- When a cloud-compiled WSE artifact fails before H2D with `baseline was not
  found in compiled artifacts`, an SDK 1.14 `SdkCompiler` `out_path` that names
  a nonexistent `.../device_artifacts/baseline` or `dynamic` directory can be
  treated as an archive rename. Pre-create the exact output directory, then
  fail closed on realpath, `cs_<sha256>` basename/root, `.csl_bin_name`, required
  archive entries, archive hash, source-tree hash, and compiler options.
- The original resident Decode ran on CS-3 but first disagreed with the frozen
  page in post-RoPE Q/K while V matched. The page carried U04 odd-lane repair;
  production `xq_rope`/`xk_rope` lost DSD offset 1 after
  `@set_dsd_base_addr`. A clearly named validation-only `B_U04_corrected`
  control made all Attention checkpoints bit-exact without modifying production
  Decode.
- Route-A FFN then first disagreed in the gate/SILU half of `ZZ_tile`: production
  f16 `/` and `value * math.inv(denominator)` are not bit-equivalent. The
  admitted solution keeps Policy-P page compute but calls a fixed 28-B resident
  wrapper at `0x2c20`; wrapper-to-compiler `__divhf3` stays resident-internal.
  All seven cloud receiver specializations must prove the section/symbol/address,
  one 168-B helper, unique return-site linkage, and no adjacent-section overlap;
  the transferred page must have no local helper or relocations.
- On P=8, bsz=1, the resulting `B_U04_corrected` and dynamic Attention→FFN
  shared-slot run completed on real CS-3. Holder catalog readback, Attention and
  FFN load/yield-command-continuation/release, 11 raw-f16 checkpoints, and final
  Z all passed; mismatch count and max absolute error were zero. Attention and
  FFN each changed all 512 output u16 values relative to the prior semantic
  state, ruling out an identity/no-compute false PASS.

## Implications / next actions

- [ ] Treat the active static choice as **Policy P + resident division service
  for bit-exact fidelity**, and keep `B_original` vs `B_U04_corrected`
  conclusions separate.
- [ ] This validated artifact identity + closure + guarded CS-3 procedure is a
  procedural skill candidate, but install it only after Le reviews the runbook.
- [ ] Do not generalize the P=8 correctness result to P=256 capacity/performance,
  Policy R, or Phase 2.

## Pointers

- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-runtime-validation/ARTIFACT_PIPELINE_AND_CS3_RUNBOOK.zh-CN.md`
- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-runtime-validation/results/p8_cs3_v7d_summary.json`
- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-runtime-validation/runs/p8-cs3-v7d-resident-fdiv/`
