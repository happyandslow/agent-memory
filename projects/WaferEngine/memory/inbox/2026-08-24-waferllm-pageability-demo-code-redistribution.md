# WaferLLM Attention→FFN pageability-demo code redistribution — 2026-08-24

**Project:** WaferEngine
**Author:** codex
**Status:** captured

## What happened / finding

- Situation: when recovering the P=256 Attention→FFN shared-slot validation from a clean `main` branch, the 20 non-production seed files can look like three copies of `Decode`. They are not a simple file split. The stable mental model is an ownership redistribution: production arithmetic is split into page entries; persistent tensors, collectives and control stay resident; loader/state/ABI/holder/filler are new infrastructure.
- Recovery checkout: `/home/lexu/WaferLLM`, branch `attn-ffn-pageability-demo`, base `main@fd1c2daae37cd68706c03fc8009887ecee9900f8`. Source snapshot: `attn-ffn-pageability@b9f5d43a581f70d905e16bcf1959dc8979101194`. The demo package is `/home/lexu/WaferLLM/pageability-demo/`.
- Production remains authoritative and immutable for four baseline CSL files plus `Decode/model_config/llama8B_4k_1_256.json`. The seed contains the other 20 frozen files. `build_sim.py` copies both into a fresh run before patching; it does not write back to production or seed.
- Of the 20 seed files, 14 are direct compiler/source closure and six are provenance-only for this build: three currently unimported `comm_layout.csl` copies plus dynamic config, manifest and Step5→F4 diff. They do not add executable bytes, but retaining them keeps the canonical 25-file lineage gate. Removing them would define a different, not-yet-revalidated snapshot.

## Logic ownership mapping

### Attention page

- `A0`: production `rmsnorm_x` square and PE-local sum; resident performs global sum.
- `A1`: remaining RMS normalization plus Q/K/V projections; resident performs fused QKV all-reduce.
- `A2`: Q/K RoPE and QK score partial; resident performs score all-reduce and route work.
- `A3`: score scale and PE-local max; resident performs global max.
- `A4`: shift, exp and PE-local sum; resident performs global sum.
- `A5`: normalize and V aggregation partial; resident performs output all-reduce.
- `A6`: O projection partial; resident performs O all-reduce.
- `A7`: Attention residual and terminal publication.

### FFN page

- `F0`: production `rmsnorm_z` square and PE-local sum; resident performs global sum.
- `F1`: normalize and UP/GATE projections; resident performs fused ZZ all-reduce.
- `F2`: SiLU and elementwise gate; continuation only.
- `F3a`: DOWN partial; resident performs DOWN all-reduce.
- `F3b`: FFN residual and terminal publication.

## File-by-file comparison for all 20 seed files

### `seed/page_attention/`

1. `decode.csl`: production-derived Attention arithmetic, renamed and split into A0–A7. Adds `.m4_page` entries, page root/dispatcher, control/continuation writes, entry-local DSD/binders, private vecmat, fixed receiver-object sections, and the page-local U04 odd-lane repair. Canonical numerical patches are applied later to the run copy.
2. `layout.csl`: keeps production P×P geometry, colors and compiler parameters. Removes model tensor host exports and adds only `m5r_attention_page_root` plus page-control exports. This is a standalone page-link harness, not the deployed dynamic layout.
3. `comm_lib/comm_layout.csl`: byte-identical to production; retained as source closure.
4. `comm_lib/comm_pe.csl`: byte-identical to production; retained for standalone compile/link closure. The transferred `.m4_page` does not own resident collectives.
5. `m5r_page_abi.csl`: new relative to production. Defines the 16-word PageControlBlock, PageId/Status/Phase and Continuation scalar contract; owns no storage, queue, route or loader.

### `seed/page_ffn/`

6. `decode.csl`: production-derived RMSNorm-Z, UP/GATE, SiLU, DOWN and residual arithmetic, split into F0/F1/F2/F3a/F3b. Adds `.m4_page`, page root/dispatcher, control/continuation and entry-local DSD. Build later routes division through the receiver and replaces local sum with explicit accumulator `@map`.
7. `layout.csl`: same page-link harness as Attention except it exports `m5r_ffn_page_root`.
8. `comm_lib/comm_layout.csl`: byte-identical to production.
9. `comm_lib/comm_pe.csl`: byte-identical to production.
10. `m5r_page_abi.csl`: byte-identical to Attention and dynamic ABI; new relative to production.

### `seed/dynamic/`

11. `src/decode.csl`: retains init/timer/decode recurrence, DSR ids and persistent tensor ownership concepts, but removes production Attention/FFN bodies. Adds shared slot, receive loader, fixed-address invoke, page-control/command arenas, D3 materializer/executor, D5 continuation binder, identity/epoch latch, load/run/release RPC and receiver data arena. Build later patches final offsets, slot size/export, diagnostics and resident fdiv.
12. `src/layout.csl`: retains the P×P receiver region and collective colors, expands to `(P+1)×P`, places holder at `(P,0)` and fillers at `(P,1..P-1)`, and adds loader color 1 serpentine routing plus dynamic exports.
13. `src/comm_lib/comm_layout.csl`: byte-identical to production.
14. `src/comm_lib/comm_pe.csl`: collective bodies are production-derived. Route/init/collective functions move to resident `.d3_runtime_code`; pointer parameters become 16-bit receiver-arena addresses that are bitcast inside the resident function.
15. `src/m5r_page_abi.csl`: byte-identical shared ABI; new relative to production.
16. `src/holder.csl`: wholly new. Owns two catalog slots, page selection, OQ2 async send, queue flush/drain, epoch/state and layout-wide load/run/release RPC surface.
17. `src/filler.csl`: wholly new no-op RPC/export shim so every role resolves and returns from the same blocking host RPC.
18. `llama8B_4k_1_256.json`: Step-6 config identity copy derived from canonical production config. The freeze-stage authoritative config is independently copied from current `Decode/model_config`.
19. `dfull_manifest.json`: new provenance record for F4 base/topology/slot/epoch policy and seven source hashes.
20. `dfull_source.diff`: new provenance evidence comparing Step-5 `D_both_profiles` with Step-6 `F4_D_full_admitted`; it is not a production diff. It records authoritative latch, admitted load/run/release, holder protocol and export changes.

## Build-time changes not present in seed

- Fresh run copies receive production-exact FFN RMSNorm/SiLU division and Attention softmax division through fixed receiver wrapper `0x2c20`.
- Baseline and page local max use explicit loop-carried accumulator `@map`; baseline and FFN page local RMSNorm sum do likewise.
- The validation baseline copy receives U04 odd-lane repair, checkpoint exports and diagnostic RPCs. Production stays byte-identical.
- Page pass0 discovers actual entry offsets, source continuation word 6 is patched, pass1 must reproduce the same offsets, and final link emits the payload.
- Dynamic source receives final slot words, page root/continuation offsets, slot export and resident fdiv retention root.
- Link results are audited for page-local helper leakage, unresolved relocation, resident wrapper/helper closure, overlap and SRAM.

## Snapshot and recovery rule

- `pageability-demo/reference/dependency_manifest.json` is a compact metadata snapshot: exact relative path, byte count and SHA-256 for all 25 frozen inputs. It is compared against a newly copied bundle, not regenerated from that same bundle.
- The file contents come from current main for four CSL files plus config and from demo seed for the other 20 files. The old commit is an independent Git recovery source.
- If the canonical manifest, the 20-file seed and the old Git object/backup are all unavailable, canonical-v5 identity cannot be proven. The safe choices are to recover a trusted snapshot or establish a new canonical snapshot only after a full fresh CS-3 validation. Never bless current hashes as expected hashes without independent provenance.

## Implications / next actions

- [ ] Before build, run only the freeze stage and require `PASS_FROZEN_DEPENDENCIES` with exactly 25 files.
- [ ] Review `/home/lexu/WaferLLM/pageability-demo/RECOVERY_RUNBOOK.zh-CN.md` stage by stage with Le before cloud/CS-3 execution.
- [ ] After successful recovery, update the code-adjacent runbook with observed artifact IDs and final evidence; do not convert old reference PASS into a fresh-run PASS.

## Update: negative economics decomposition and optimization points

- The canonical dynamic receiver is 32,054 B allocated versus 28,872 B for the corrected baseline. Its `.m4_page` section is a full 4,096 B. Holding every other measured resident section constant gives a slot-excluded floor of 27,958 B, so a finer-grained maximum slot plus any newly added resident metadata must be below **914 B** merely to beat baseline allocated union. This is a measured break-even bound, not an estimate of entry size.
- The negative result must be separated into three hypotheses: remote-loading mechanism floor; phase-sized load-unit selection (8 Attention entries and 5 FFN entries resident together); and correctness-first implementation overhead (repeated control stores, root dispatch, hard-coded D3/D5 tuples, and fixed-placement holes). Existing evidence proves only that the current phase-page construction is negative, not that paging is fundamentally negative.
- Potential optimization/audit points are recorded: linked entry closure sizes; entry-page and continuous-superpage partition sweep; immutable page metadata table; direct validated entry-offset calls without root dispatch; D3/D5 table compression; page-local pinned-address DSD versus resident DSD thunk comparison; fixed-section repacking; and optional next-entry prefetch during resident collective with independent color/quiescence proof.
- Page-local DSD construction against pinned receiver addresses is a valid `abi-pinned` design and is already used for local compute. Its tradeoff versus receiver-resident DSD handles is page setup bytes and tighter address/shape ABI versus receiver SRAM, validation, and descriptor reuse. A likely hybrid keeps compute DSDs page-local while resident collectives accept audited buffer ids.
- Workflow decision from Le: defer every optimization implementation and experiment until the minimal demo has completed the full fresh recovery sequence (`freeze`, `build`, artifact registration, baseline, dynamic protocol, raw-u16 compare, final audit). During recovery, agents may append newly observed optimization evidence to the backlog but must not change page granularity, DSD ABI, metadata, dispatcher, state machine, or placement. After `PASS_P256_MAP_MAX_SHARED_SLOT_E2E`, return first to the linked entry-closure audit rather than immediately implementing an optimization.

## Pointers

- `/home/lexu/WaferLLM/pageability-demo/docs/CODE_REDISTRIBUTION.zh-CN.md`
- `/home/lexu/WaferLLM/pageability-demo/docs/PAGING_NEGATIVE_ECONOMICS_QUESTIONS.zh-CN.md`
- `/home/lexu/WaferLLM/pageability-demo/RECOVERY_RUNBOOK.zh-CN.md`
- `/home/lexu/WaferLLM/pageability-demo/SOURCE_SNAPSHOT.json`
- `/home/lexu/WaferLLM/pageability-demo/reference/dependency_manifest.json`
- `/home/lexu/WaferLLM/pageability-demo/scripts/build_sim.py`
- `projects/WaferEngine/memory/inbox/2026-08-24-waferllm-attn-ffn-code-snapshot.md`
- `projects/WaferEngine/memory/inbox/2026-08-24-meshjit-p256-shared-slot-e2e-pass.md`
