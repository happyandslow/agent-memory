# MeshJIT Phase 1 joint ownership + MeshRT eight-operator audit — 2026-08-13

**Project:** WaferEngine
**Author:** codex
**Status:** captured

## What happened / finding

- WaferLLM Decode Phase 1 Steps 1–2 completed at WaferLLM revision
  `fd1c2daae37cd68706c03fc8009887ecee9900f8` with the frozen function-container
  design SHA-256 `edbac709d573ae4bbe55caa2377494ca62dee01a78143800662f9c3916debc38`.
  Controlled SDK-2.10 final-link images B/A_attn/A_ffn/A_both used the
  production-shaped `llama8B_4k_1_256.json` (`P=256`, `bsz=1`).
- Complete receiver data-bank high-water deltas were Attention **5,088 B**,
  FFN **2,256 B**, and joint **10,432 B**. Thus interaction is
  `5,088 + 2,256 - 10,432 = -3,088 B`. The negative sign means 3,088 B are
  shared closure released only when both boundaries are removed: 2,768 B
  `.text`, 160 B `.data.lo`, 46 B `.data`, 112 B `.bss`, and 2 B alignment.
  It is not negative savings, payload size, or a quantity assignable to either
  page. The final complete image B/A_attn/A_ffn/A_both is
  25,728/20,640/23,472/15,296 B. The B/A absence images retained genuine
  `decode_entry` and route continuation only; no shadow phase compute.
- Shared final-link closure includes generic `vecmat_computation` / `@map`
  lowering, generic DSD/pointer state, RMSNorm state, arithmetic lowering
  (`__divhf3`), and inlined continuation traversal. `vecmat_computation`
  (228 B) and `__divhf3` (168 B) survive both individual removals and vanish
  only in A_both. All 25 compute ELF records had uniform deltas and no final
  relocations.
- In parallel, the paper’s four MeshRT models were audited in the exact public
  `CongjieHe/meshRT-csl` `che/paper-exp` revision
  `52a881c4984bd5db9ed25582d609dde888b989a8`: Qwen3.5-Dense-9B,
  Qwen3.5-MoE-35B-A3B, GPT-OSS-MoE-20B-A4B, GPT-OSS-MoE-120B-A5B, each at its
  selected prefill and decode source/config (8 targets total).
- All eight MeshRT targets are **source-only grade S**. Their whole scheduler
  bodies have normal helper, fabric DSD, task/async, queue, route, and (for
  MoE) dispatch/combine closure, therefore classify as
  `unsupported-current-loader` without resident thunks. No linked bytes,
  removable ownership, gaps, or SRAM delta is known.
- The MeshRT B/A relink gate did not run: local SDK-2.10 `cslc` and
  `cs_python` fail before compiler start because the Singularity wrapper lacks
  FUSE and its unprivileged extraction fallback has no setuid installation.
  No checked-in ELF/map artifacts exist. This is an environment/toolchain
  blocker, not a hardware or compiler-quality conclusion.

## Implications / next actions

- [ ] For WaferLLM only, discuss Phase 1 Step 3 page-region manifests: two
  address-matched multi-entry regions with no normal calls to receiver code;
  collectives/routes/tasks stay behind resident command/continuation thunks.
  This remains `REVISE / evidence-incomplete`, not GO-performance or GO-capacity.
- [ ] On a host where MeshRT SDK can launch, perform per-target final-link B,
  A_attention, A_ffn and A_both relinks before making any SRAM claim. Preserve
  source/ELF evidence grades separately.

## Pointers

- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/README.md`
- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/JOINT_OWNERSHIP.md`
- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/results/sram_comparison.json`
- `/tmp/meshrt-eight-operator-audit/README.md`
- `/tmp/meshrt-eight-operator-audit/audit_summary.json`
- `/tmp/meshrt-eight-operator-audit/MEASUREMENT_STATUS.md`
