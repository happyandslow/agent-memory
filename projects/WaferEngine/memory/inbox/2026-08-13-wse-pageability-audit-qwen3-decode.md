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

## Proposed multi-page ABI-profile architecture — 2026-08-13

For `vecmat`, Q+K RoPE, and softmax, the intended end state is not one body-sized receiver reservation per function. It is one common loader and shared executable slot, a small number of reusable resource profiles, and function-specific page bytes plus a compact manifest.

- **Common loader/runtime:** one maximum-sized executable slot; a code receive IQ/DSD bound directly to the slot; completion task; `invoke_slot`; safe overwrite/drain protocol; small command arena and resident command dispatcher for operations that pages must not execute directly (especially collectives and route/task state).
- **Common scalar ABI example:** `opcode`, `loop_bound`, `output_len`, `batch`, `segment`, `command_count`, `flags`, and one reserved field. This control block is not the whole ABI: tensor buffers, DSD setup, DSR kinds, queues, and thunks remain separately accounted.
- **GEMV profile (`vecmat` pages):** receiver wrapper selects X/W/out bases and `Kt/Nt`, constructs or updates local memory DSDs, and loads the agreed GEMV DSR set. The page performs the compute traversal. The open correctness issue is whether the left-vector `@map` traversal can be expressed using only preloaded DSR state or still requires a pinned DSD object/page-local lowering.
- **RoPE profile:** receiver binds Q/K, sin/cos, temporaries, and the agreed DSR1--6 calling convention. A page should ideally perform only arithmetic/traversal over that profile. Current RoPE reuses DSR5 for different DSD bindings, so page-local `@load_to_dsr` retains DSD closure unless the implementation allocates separate preloaded DSRs, calls a resident binding thunk, or splits the page at binding transitions.
- **Softmax profile:** do not treat the collective-bearing function as one direct page. Split it into local-max compute, exp/local-sum compute, and normalize compute pages, with resident max/sum all-reduce thunks between them. The page manifest declares the required resource profile and any resident command/synchronization boundary.

Illustrative execution order:

```text
load vecmat page -> invoke repeatedly for Q/K/V -> resident collective as needed
load RoPE page   -> invoke Q and K under the RoPE profile
load vecmat page -> invoke score projection
load softmax local-max page -> resident max all-reduce
load softmax exp/sum page    -> resident sum all-reduce
load softmax normalize page
```

Per-page manifest fields should include at least: page name, transferred/aligned words, slot/source address assumptions, ABI profile id, DSR ids/kinds, runtime scalar fields, resident commands/thunks, normal helper calls, and whether address matching is required.

Economic gate: this architecture is beneficial only if reusable common-profile retention plus `max(page size)` is smaller than the sum of removable resident ownership. If each page introduces a near-body-sized `reserve_<function>_abi`, the design has failed even if dynamic execution is correct. Measure with baseline/body-absent/dynamic receiver images; do not infer savings from page bytes.

### DSD/DSR binding strategies to revisit

| Strategy | Dynamic page behavior | Resident requirement | Principal limit / gate |
| --- | --- | --- | --- |
| Page-local DSD loads | Page executes `@load_to_dsr` and may rebind DSRs internally | Pin every addressed DSD/global and reserve DSR ids/kinds | Large page-specific cross-ELF closure; addresses/layout must match |
| Pre-bound DSR profile | Receiver configures DSDs and loads a fixed DSR calling convention before page entry; page performs only compatible compute/traversal | Reusable profile setup and reset code | Finite DSR resources; intra-page/data-dependent rebinding and some `@map` lowering may not be expressible from entry state alone |
| Resident binding thunk | Page returns/emits a command; receiver reconfigures local DSD/DSR state and invokes a continuation | Shared descriptor templates, dispatcher/thunk, continuation state | More resident control code and boundaries; direct page-to-thunk calls remain an unverified helper-call ABI unless separately proved |
| Split pages | Divide at DSR rebinding, collective, or synchronization boundaries | Common loader/profile setup at each boundary | More dispatches and possibly more page loads; simplest correctness closure |

Do not assume a fixed/bounded source-level DSR count automatically makes pre-binding best. Measure the linked common profile against controlled page-specific reservation. Small metadata is not the full cost: include DSD templates, metadata interpreter/binder, DSR-kind retention, reset code, and synchronization. Conversely, a reusable binder profile can amortize across many pages, while a `reserve_<function>_abi` stub is page-specific and can approach the removed-body cost.

Softmax clarification: three compute pages imply up to three loads only when they are mutually exclusive payloads occupying one slot (`local_max` then max all-reduce, `exp_sum` then sum all-reduce, then `normalize`). A collective thunk does not intrinsically evict the current page. One load is possible if a single multi-entry/multi-stage softmax page remains in the slot and resident code safely resumes it using an explicit phase/continuation ABI; that mechanism is not yet validated for the current loader.

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

## Attention/FFN shared-slot design checkpoint — 2026-08-13

- The function-container scope was narrowed to exactly two address-matched, multi-entry page regions: one whole Attention phase and one whole FFN phase sharing one receiver executable slot. `vecmat`, RoPE, and softmax are no longer independent loading targets; they are internal closure/profile problems inside the two pages.
- Collectives, queue/task state, route repaint/fence, and completion remain receiver-resident behind a command/continuation ABI. The initial model loads Attention once for A0--A7 and FFN once for F0--F3, for two loads per layer.
- Phase 2 implementation is gated on Phase 1 final-linked economics: joint body-absent ownership, complete container/profile floor, positive receiver `net_free` with margin, a concrete same-PE use for the bytes, pessimistic modeled benefit exceeding load/continuation overhead, and a plausible communication admission schedule.
- The next session is authorized to perform only Phase 1 Steps 1--2: freeze baseline and construct comparable `B`, `A_attn`, `A_ffn`, and `A_both` images, explain individual-vs-joint ownership interaction, then stop for review. It must not build page payloads or runtime code.
- Checkpointed at WaferLLM `fd1c2daae37cd68706c03fc8009887ecee9900f8`. Design SHA-256: `edbac709d573ae4bbe55caa2377494ca62dee01a78143800662f9c3916debc38`.

Pointers:

- `/home/lexu/WaferLLM/MeshJit-Decode/FUNCTION_CONTAINER_DESIGN.md`
- `/home/lexu/WaferLLM/MeshJit-Decode/FUNCTION_CONTAINER_CHECKPOINT.md`
- `/home/lexu/WaferLLM/MeshJit-Decode/PHASE1_STARTING_PROMPT.md`
