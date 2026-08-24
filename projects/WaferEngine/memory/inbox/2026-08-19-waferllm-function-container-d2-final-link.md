# WaferLLM function-container D2 final-link receiver floor — 2026-08-19

**Project:** WaferEngine  
**Author:** codex  
**Status:** drained 2026-08-21 into `memory/topics/meshjit-code-relocation.md` and `plan.md`

## Situation / finding

When measuring the common receiver floor after the direct-to-slot D1 loader,
D2 must add a scalar page ABI, page selection/invoke seam, and command storage
without duplicating D1 status, copying the page dispatcher outside the slot, or
silently implementing D3 command/continuation runtime.

The validated controlled ladder is:

| Image | Max final-linked allocated union | Marginal |
|---|---:|---:|
| D1c baseline | 20,426 B | — |
| D2a canonical control | 20,460 B | +34 B |
| D2b invoke/phase selection | 20,640 B | +180 B |
| D2c bounded command arena | 20,700 B | +60 B |

Thus official D2 costs **274 B over D1** at SDK 2.10, Route-A/P, P=256,
bsz=1. The metric is the maximum union of all SHF_ALLOC ranges below `0xc000`,
including NOBITS and the 1-KiB task table; fixed gaps and high-water are tracked
separately.

D2a replaces the D1 one-word state with the canonical 16×u16 PageControlBlock
at `0x7000`; status is word 15, so no permanent double status exists. D2c
reserves 10×u16 at `0x7020`: `op_count,cursor` plus two four-word operation
records. Capacity two is derived from the maximum ordered-operation count among
the ten frozen M2 sequences. D3 owns population and execution.

The receiver invoke wrapper is fixed at `.d2_invoke_code @0x2c00`. It validates
ABI version, BOUND/YIELDED state, yielded epoch, and page ID, then tail-calls the
page-local root rather than slot byte zero. Reviewed Route-A/P v4 roots are:

- Attention: `0x1a00 + 4184 = 0x2a58`, uniform across 52 page ELFs;
- FFN: `0x1a00 + 2272 = 0x22e0`, uniform across 38 page ELFs.

SDK SIF `elf2am` audited all 34 D2b and 36 D2c receiver ELFs. Every
`.d2_invoke_code` instruction is covered; each specialization has exactly one
Attention and one FFN fixed-root tail call and no unapproved non-return register
jump.

## Non-obvious admission lesson

The first independent review found that numerically correct reports were not
enough: a stale report could survive source, ELF, or specialization removal.
The final PASS chain therefore binds and rehashes the complete five-file CSL
source tree, build script, SDK compiler, compile log, `out.json`, exact
34/34/34/36 ELF name/hash inventories, SRAM extracts, machine-audit script/SIF/
report, and all 52/38 reviewed Step-3 raw page ELFs plus their policy, compile
commands, source trees, review-fix evidence and independent-review provenance.
After a fresh four-image rebuild, re-review returned `PASS — no actionable
findings remain`.

The inherited `d1_mark_evictable` remains only a READY-state audit seam. It is
a no-op for RUNNING/YIELDED and is not D3 terminal quiescence; D3 must replace
or extend it.

## Evidence and limits

- Grade E static final-link and machine-control-flow evidence only.
- No payload transfer, page execution, resident command execution, continuation
  reinvocation, Step-5 profile/DSD/DSR union, simulator/device correctness,
  latency, or dynamic net-saving claim.
- Production `Decode/` remains unchanged; WaferLLM revision is
  `fd1c2daae37cd68706c03fc8009887ecee9900f8`.

## Pointers

- Result: `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step4-common-floor/d2/D2_RESULT.zh-CN.md`
- Decomposition: `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step4-common-floor/d2/D2_DECOMPOSITION.zh-CN.md`
- Complete-image JSON: `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step4-common-floor/d2/results/d2_sram_comparison.json`
- Machine invoke JSON: `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step4-common-floor/d2/results/d2_machine_invoke_audit.json`
- Final validation: `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step4-common-floor/d2/results/d2_validation.json`

## Next action

Stop before D3. D3 must measure the marginal complete-image cost of minimal
resident command execution, completion wait, continuation reinvocation, and
terminal quiescence; it must not reuse the READY-only D1 seam as proof.
