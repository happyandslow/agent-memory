# WaferLLM function-container D1 final-link receiver floor — 2026-08-18

**Project:** WaferEngine  
**Author:** codex  
**Status:** captured

## Situation / finding

When adding the Step-3 Attention/FFN slot to the body-absent Decode receiver,
raw Phase-1 `A_both` cannot be used directly: its monolithic `.bss`
`0x1544–0x37f1` overlaps the address-matched slot
`0x1a00–0x2aff`. SDK 2.10 also ignores a requested placement for the standard
`.bss` section. A second failure showed that leaving the growing loader in
ordinary `.text` pushes the fixed 1-KiB task table 64 B into the slot.

The validated D1 construction therefore starts from the already-audited
Step-3 receiver-shaped `A_both`: retain the canonical 32-object receiver data
arena, deterministically remove the existing 16-word page-control block and
old 4,096-B slot, then add exactly one 4,352-B `.m4_page` slot. Loader code is
isolated at `.d1_loader_code @0x2b00`; the one-word state is at
`.d1_loader_state @0x7000`; the arena remains at `0x4000`. This preserves the
Step-3 page/data ABI without importing D2 control into D0.

SDK 2.10 production-shaped P=256 final links passed for all four controlled
images. The maximum final-linked allocated union below `0xc000`, including
NOBITS and task table, is:

| Image | Bytes | Marginal |
|---|---:|---:|
| D0 | 20,060 | — |
| D1a transport | 20,184 | +124 |
| D1b local completion | 20,354 | +170 |
| D1c overwrite safety | 20,426 | +72 |

Thus canonical D1 costs **366 B over D0**. The fixed slot (4,352 B), receiver
arena (9,338 B), BSS (334 B), and task table (1,024 B) are identical across all
images. Transport adds `.data.lo +8`, `.text +32`, and 84 B loader code.
Completion adds `.text +112`, `.data -8`, 64 B loader code, and 2 B state.
Overwrite safety adds `.text +44` and 28 B loader code.

The direct destination DSD is constructed over the slot itself and SDK accepts
the synchronous `@mov32`; no `code_dst_dummy`, payload-sized staging object,
second slot, async completion task, page body, invoke, dispatcher, command
arena, or continuation runtime is present. Status IDs are frozen at
EMPTY=0/LOADING=1/READY=2/EVICTABLE=7. Invalid load states do not receive or
write. READY never auto-releases; `mark_evictable` is only a seam for a future
D3 quiescence owner.

## Color/queue conclusion

Color 1 is a router channel ID, not an address. The future holder's local OQ2
injects one 1,088-u32 stream; every receiver's local IQ2 consumes one router
tap. Queue index 2 is a separate local resource on each PE; intermediate
compute PEs forward in router hardware and do not software-relay through OQ2.

A source-faithful adapter for the legacy direct-cslc WaferLLM harness passed:
production Decode uses colors 5–9 and IQ/OQ3–7, while SDK memcpy reserves
colors 20–23. D1's static color1/receiver-IQ2 choice is disjoint, and the holder
endpoint contract fixes OQ2/count=1,088. This is D1 receiver admission only.
Holder catalog/filler final link, OQ drain, global all-receiver completion,
repeated-load ordering, and post-page quiescence remain Step-9 obligations.

## Evidence and limits

- Grade E: final-linked ELF/section/symbol/relocation and complete-image
  accounting for every compiler specialization.
- No simulator/device run, transferred-page execution, numerical correctness,
  latency, dynamic receiver saving, D2/D3, or Phase 2 claim.
- Failed and interrupted attempts are preserved in the D1 failure ledger; none
  were attributed to hardware.

## Pointers

- Result:
  `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step4-common-floor/D1_RESULT.zh-CN.md`
- Machine-readable comparison:
  `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step4-common-floor/results/d1_sram_comparison.json`
- Color/queue adapter evidence:
  `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step4-common-floor/results/d1_color_queue_audit.json`
- Failure ledger:
  `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step4-common-floor/FAILURE_LEDGER.md`

## Next action

Stop and review D1 before D2. D2 must replace the temporary D1 status word with
one authoritative page-control storage; it must not retain a permanent duplicate.
