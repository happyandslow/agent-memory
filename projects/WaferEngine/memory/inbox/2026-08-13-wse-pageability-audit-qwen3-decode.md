# WSE pageability audit skill + Qwen3 decode application — 2026-08-13

**Project:** WaferEngine
**Author:** codex
**Status:** captured

## What happened / finding

- When assessing whether arbitrary CSL kernel functions can become MeshJIT pages, source closure, linked symbol bytes, removable ownership, and dynamic-receiver SRAM must be kept as separate evidence grades. A reusable `wse-pageability-audit` skill was installed under `/home/lexu/claude-skills`; it audits calls, globals, memory/fabric DSDs, DSR ids/kinds, tasks/async/fabric operations, control flow, ELF symbols/sections/relocations, cross-ELF payload hashes, and color-audit admission state.
- Applied at local `happyandslow/WaferEngine` commit `fcfc8c1` to `models/qwen3_1p7b-e2e-pdSeparate/src/decode`, SDK-2.10 compile-only config `test_sim_1x2blk_kv.json`. Best first direct candidate is `rope_kernel`: 600 B linked, 8 memory DSDs, DSR ids 1--6, no normal helper or fabric DSD. `vecmat_computation_f32` is 236 B with 3 memory DSDs, DSR id 1, and one `@map`; useful for correctness but weak alone economically.
- Equal-size candidate symbols were not byte-identical across the four compute PE ELFs. `rope_kernel`, `vecmat_computation_f32`, and `qk_norm_phase1` each had 4 distinct payload SHA-256 values across 4 matched ELFs; their addresses also differed by 8 B between variants. One payload cannot be assumed multicast-safe across all compute PEs until ABI/placement is pinned or receiver groups are specialized.
- `csl-color-audit` covered all 30 `decode_layer_body` stages. Sixteen colors were lifetime-free in that view, but none of IQ0--IQ7/OQ0--OQ7 was free/unbound at any stage. A loader needs a proved drain + queue rebind + route repaint/fence (or a compatible existing transport); free color alone is insufficient.
- Whole `decode_layer_body` is 3,600 B but crosses collectives, route repaint, helper calls, and fabric closure. It is not a direct page under the validated loader. `rmsnorm_kernel` (844 B) and `softmax_score` (892 B) are better treated as compute-page + resident-thunk transformations.
- These are grade-E source/ELF findings, not SRAM savings. Controlled body-absent ablation, dynamic receiver, candidate-absence proof, bit-exact execution, and load/use timing remain undone.

## WaferLLM Q+K RoPE follow-up — 2026-08-13

- The current WaferLLM `Decode/src/decode.csl` `xq_rope()` + `xk_rope()` bodies were normalized and fused into one address-matched `rope_kernel` in the isolated `MeshJit-Decode/rope-page/` harness. The candidate contains only memory DSD/DSR hardware operations and no normal module call.
- SDK-2.10 simulator correctness passed: the holder sent the exact 1,068-B / 267-u32 resident ELF payload from `0xa000` into a 1,280-B receiver slot at `0xa000`; the receiver ELF had neither `.cand_rope` nor a candidate symbol; all 48 fp16 QKV elements were resident-vs-relocated bit-exact on nontrivial signed inputs, and V remained unchanged.
- Pinned initial images matched: `.rope_data` was 192 B at `0x8000`; `.rope_abi` was 10 B at `0x8800`. Final ELF relocation tables were empty.
- The isolated three-image section accounting is a negative economic result. With an exact 267-word / 1,068-B slot: resident 4,496 B, body-absent 3,852 B, dynamic receiver 6,096 B; removable ownership 644 B, dynamic admission floor 2,244 B, and net receiver saving **-1,600 B**. The body-absent DSR/DSD reservation raised `.text` by 424 B and the slot plus loader state dominated. An earlier 320-word growth slot produced -1,812 B. These are isolated linked-section sums, not production Decode total SRAM or a timing result.
- Durable lesson: `abi-pinned` means the relocation closure is tractable, not that offload is economically attractive. Candidate bytes must not be reported as saved SRAM; the body-absent reservation can materially reduce removable ownership.

## Implications / next actions

- [x] Build an isolated WaferLLM one-receiver holder/body-absent proof for the combined Q+K RoPE boundary, address-matched with pinned DSD/global/DSR ABI.
- [x] Measure isolated baseline/body-absent/dynamic linked-section deltas.
- [ ] Substitute the page into a full WaferLLM Decode phase and repeat complete-PE SRAM accounting; do not reuse the isolated harness delta as a production claim.
- [ ] Add on-device TSC load/use timing only after the full-Decode correctness gate.
- [ ] Audit a concrete queue drain/rebind/repaint/fence boundary for loader admission.

## Pointers

- `/home/lexu/claude-skills/wse-pageability-audit/`
- `/home/lexu/WaferLLM/pageability-audits/qwen3_1p7b-e2e-pdSeparate-decode/ASSESSMENT.md`
- `/home/lexu/WaferLLM/pageability-audits/qwen3_1p7b-e2e-pdSeparate-decode/pageability.json`
- `/home/lexu/WaferLLM/MeshJit-Decode/rope-page/README.md`
- `/home/lexu/WaferLLM/MeshJit-Decode/rope-page/results/validation_test_rope.json`
- `/home/lexu/WaferLLM/MeshJit-Decode/rope-page/results/elf_audit_test_rope.json`
- `/home/lexu/agent-memory/projects/WaferEngine/assets/pageability-audit/2026-08-13-qwen3-decode/CONCLUSION.md`
- `/home/lexu/agent-memory/projects/WaferEngine/assets/pageability-audit/2026-08-13-qwen3-decode/2026-08-13-qwen3-decode-pageability.tar.zst` — complete 417-file audit + skill snapshot; SHA-256 `bc2f0c8a928c3ce3ed1e0761cb8dabae845ca23694872e5eb71adef393bb7d18`
- `/home/lexu/agent-memory/projects/WaferEngine/assets/pageability-audit/2026-08-13-qwen3-decode/MANIFEST.sha256`
- `/home/lexu/agent-memory/projects/WaferEngine/memory/topics/meshjit-code-relocation.md`
