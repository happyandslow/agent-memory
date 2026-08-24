# WaferLLM function-container D3 resident runtime floor — 2026-08-19

**Project:** WaferEngine  
**Author:** codex  
**Status:** drained 2026-08-21 into `memory/topics/meshjit-code-relocation.md` and `plan.md`

## Situation / finding

When a Decode receiver has a direct-to-slot loader, canonical 16-word page
control block, fixed page-root invoke seam, and a bounded two-record command
arena, D3 must add the smallest resident command/continuation runtime without
silently owning the Step-5 profile binder or claiming transferred-page
correctness.

Under SDK 2.10, Route-A/P, P=256 and bsz=1, the reviewed controlled ladder is:

| Image | Max final-linked allocated union | Marginal |
|---|---:|---:|
| D2c baseline | 20,700 B | — |
| D3p runtime placement | 20,708 B | +8 B |
| D3a sequence materializer | 22,584 B | +1,876 B |
| D3b resident executor | 28,598 B | +6,014 B |
| D3c continuation reinvoke | 29,338 B | +740 B |
| D3d terminal quiescence seam | 29,470 B | +132 B |

Official D3 therefore costs **8,770 B over D2**. The metric is the maximum
union of all SHF_ALLOC ranges below `0xc000`, including NOBITS and the 1-KiB
task table. The fixed `.d3_runtime_code @ 0x7100` is 9,312 B; D2 invoke code in
the official image is 112 B.

D3a recognizes exactly the 13 M2 yield tuples and materializes at most two
ordered resident operations. D3b maps the 11 operation/buffer/axis/flags keys
to the production collective and route functions. D3c consumes, but never
creates, Step-5 `BOUND`; it validates the 13-entry page/entry/profile allow-list,
epoch, and initial-versus-resumed command-arena history before reinvoking a
fixed page root. D3d maps MARK_DONE to DONE and requires a six-condition,
epoch-matched external quiescence attestation before EVICTABLE.

SDK `elf2am` audited all 36 official receiver specializations: 2,328 runtime
instructions plus the D2 invoke seam had complete coverage, no unapproved
external helper escape, and calls only to the resident runtime or the two frozen
page roots. D3 adds no color token, queue initialization, queue flush, or route
rebind.

## Non-obvious failure modes and fixes

- Repeated host RPC can replay collectives unless materialization requires a
  fresh `(op_count=0,cursor=0)` arena and resumed entries require a completed
  prior arena.
- A compound CSL arena predicate was lowered into slot-external
  `__ld16_align1/__st16_align1`; fixed-index sequential checks kept the closure
  inside `.d3_runtime_code`.
- Keeping the inherited `d2_invoke_page` RPC exposed bypassed the D3 BOUND,
  epoch, and arena guards. Official D3 removes that export; `d3_run_step` is the
  sole external page-entry path.
- Fail-closed tests must parse generated source, not only manifests: the final
  validator exercises 13 materializer positives/117 mutations, 13 BOUND
  allow-list positives/39 mutations, 8 reinvoke cases, 11 executor cases/44
  key mutations, and the six terminal conditions/6 mutations.

The independent review-fix loop ended with the verbatim result `No findings`.

## Evidence and limits

- Grade E static final-link and machine-control-flow evidence only.
- No transferred page was executed. Collective/queue completion, all-receiver
  quiescence, numerical correctness, latency and dynamic net saving remain
  unproven.
- Step 5 remains the sole owner of the real DSD/DSR profile reservation union
  and `YIELDED -> BOUND` binding transition.
- Production `Decode/` remains unchanged; WaferLLM revision is
  `fd1c2daae37cd68706c03fc8009887ecee9900f8`.

## Pointers

- Result: `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step4-common-floor/d3/D3_RESULT.zh-CN.md`
- Decomposition: `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step4-common-floor/d3/D3_DECOMPOSITION.zh-CN.md`
- Review history: `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step4-common-floor/d3/INDEPENDENT_REVIEW.md`
- Complete-image JSON: `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step4-common-floor/d3/results/d3_sram_comparison.json`
- Machine audit: `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step4-common-floor/d3/results/d3_machine_runtime_audit.json`

## Next action

Stop before Step 5. Measure the minimal per-entry DSD/DSR reservation union and
implement the binder that owns `YIELDED -> BOUND`; do not start transferred-page
runtime execution in this step.
