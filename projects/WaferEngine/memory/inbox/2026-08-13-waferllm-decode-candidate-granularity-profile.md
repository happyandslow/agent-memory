# WaferLLM Decode dynamic candidate granularity profile — 2026-08-13

**Project:** WaferEngine
**Author:** codex
**Status:** captured

## What happened / finding

- When selecting the next real shared-slot candidate after the physical vecmat
  proof, the SDK-2.10 main Decode source was profiled at the production-shaped
  `llama8B_4k_1_256` compile-time configuration. Baseline compute `.text` is
  14,480 B.
- Final-link removal deltas (code-ownership upper bounds) were: whole attention
  4,656 B; whole FFN 1,768 B; Q+K RoPE pair 1,056 B; softmax 996 B; score phase
  836 B; QKV phase 816 B; up+gate phase 736 B; RMSNorm X/Z 656/648 B;
  SiLU+z3 192 B.
- These are not linked candidate sizes. Deleting a phase also dead-strips code
  unique to that phase; a large delta can span helper calls, collectives, route
  reconfiguration, and many globals.
- The best next correctness boundary is combined Q+K RoPE: meaningful code
  ownership, no normal helper or `comm_mod` calls, and only DSD/DSR/hardware
  arithmetic. It still requires a medium-sized ABI reservation for QKV,
  frequency/temp DSDs, and DSR kinds 1--5.
- Whole attention + whole FFN is the largest theoretical mutually-exclusive
  pair: 6,424 B individual ownership and at most 1,768 B gross shared-slot
  saving before admission costs. Current remote-loading proof does not support
  this closure; it needs monolithic phase images, a validated call-to-resident
  helper ABI, or a multi-section closure loader.
- A low-compute function is not automatically favorable: short use time makes
  load/use worse. Rank by removable bytes per phase load, phase reuse, helper
  closure, and resident ABI floor.

## Implications / next actions

- [ ] TSC-profile vecmat/projection reuse, Q+K RoPE, softmax, attention phase,
  and FFN phase before making a performance claim.
- [ ] Add Q+K RoPE as the next real shared-slot correctness candidate.
- [ ] Independently reduce the one-map admission floor.

## Pointers

- `/home/lexu/WaferLLM/MeshJit-Decode/candidate-profile/ASSESSMENT.md`
- `/home/lexu/WaferLLM/MeshJit-Decode/candidate-profile/results/static_llama8B_4k_1_256.json`
- ContextBase: `https://context.ed-aisys.com/doc/2026-08-13-result-waferllm-decode-vecmat-cs-3-proof-candidate-profile-jW0t55xcx5`
