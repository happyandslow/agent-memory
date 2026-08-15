# WaferLLM Decode Attention/FFN joint removable ownership — 2026-08-13

**Project:** WaferEngine
**Author:** codex
**Status:** drained

## What happened / finding

- When deciding whether one address-matched executable slot can be shared by
  whole Decode Attention and FFN phases, source/function byte counts were not
  sufficient. A controlled SDK-2.10 final-link study at WaferLLM
  `fd1c2daae37cd68706c03fc8009887ecee9900f8`, production-shaped
  `llama8B_4k_1_256.json` (`P=256`, `bsz=1`), compared the original receiver
  `B` with `A_attn`, `A_ffn`, and `A_both` body-absent images.
- The complete normal receiver data-bank high-water deltas were Attention
  **5,088 B**, FFN **2,256 B**, and joint **10,432 B**. Thus
  `interaction = 5,088 + 2,256 - 10,432 = -3,088 B`: removing both releases
  3,088 B more than the individual removals sum. Old `.text` figures 4,656 B
  and 1,768 B are only their `.text` components, not the final ownership result.
- The extra joint release is measured as 2,768 B `.text`, 160 B `.data.lo`,
  46 B `.data`, 112 B `.bss`, and 2 B changed alignment gap. Shared closure
  includes generic `vecmat_computation`/`@map` lowering, DSD/pointer state,
  RMSNorm state, arithmetic lowering, and inlined `decode_entry` traversal.
  `vecmat_computation` (228 B) and `__divhf3` (168 B) remain in both individual
  images and disappear only in `A_both`.
- `A_both` still occupies **15,296 B** (5,288 B `.text`, 8,878 B `.bss`, full
  1,024-B task table, fixed runtime sections). This is removable ownership
  evidence (grade A), not a dynamic receiver net saving: page payloads, a slot,
  loader/continuation/profile floor, dynamic correctness, and performance remain
  unmeasured.
- The body-absent sources retain only the genuine `decode_entry()` recursion and
  required Y-route continuation; no placeholder Attention/FFN compute,
  projection, collective, or shadow `@map` traversal is used. All 25 generated
  compute ELF records had uniform deltas and no final ELF relocations.

## Implications / next actions

- [ ] Discuss design-doc Phase 1 Step 3 only: whether separately linked,
  address-matched Attention/FFN page regions can represent the measured
  ownership without retaining a near-copy of the shared closure. Do not start
  this without the Phase 1 gate decision.

## Pointers

- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/README.md`
- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/JOINT_OWNERSHIP.md`
- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/results/sram_comparison.json`
- `/home/lexu/WaferLLM/MeshJit-Decode/FUNCTION_CONTAINER_DESIGN.md`
