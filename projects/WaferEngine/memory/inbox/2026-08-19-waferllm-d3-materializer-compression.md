# WaferLLM D3 materializer compression — 2026-08-19

**Project:** WaferEngine  
**Author:** codex  
**Status:** drained 2026-08-21 into `memory/topics/meshjit-code-relocation.md` and `plan.md`

## Situation / finding

When the resident D3 command materializer contains repeated ten-word arena
clears and schema-complete zero stores, source sparsity does not predict SRAM
savings. Under the reviewed Route-A/P, SDK 2.10, P=256, bsz=1 D3d receiver,
three controlled production-shaped variants gave:

| Variant | Complete receiver | Delta vs 29,470-B D3d | Materializer | Machine closure |
|---|---:|---:|---:|---|
| Sparse writes + full ten-word freshness guard | 29,506 B | +36 B | 1,868 B | PASS |
| Sparse writes + existing two-word header guard | 29,410 B | -60 B | 1,772 B | PASS |
| 13×10-word descriptor table + generic copy loop | 30,390 B diagnostic | +920 B | 1,852 B | FAIL |

The full freshness guard costs more compare code than it removes in stores. The
two-word-guard variant saves 60 B only because the current runtime has a stronger
implicit invariant: every transition publishing `(op_count,cursor)=(0,0)` clears
words 2..9 as well. It is a candidate, not the selected official D3 image, until
that invariant becomes authoritative and the revised image receives independent
review.

The descriptor-table design fails the official placement before admission:
`.task_table=0x1670..0x1a6f` overlaps the fixed `.m4_page=0x1a00..0x2aff` by
112 B. A diagnostic-only shifted link attributes its +920 B to +288 B
`.d3_runtime_code`, +260 B BSS table, and +372 B ordinary `.text`. The added
text includes a 240-B `memcpy`, 44-B `__ld16_align1`, and 80-B
`__st16_align1`; WSE `elf2am` proves one forbidden `.d3_runtime_code -> .text
memcpy` call in each of 36 specializations. Thus the aggressive table approach
is both larger and incompatible with the current no-external-helper closure.

## Evidence and limits

- Evidence is Grade E compile/link plus WSE machine-control-flow audit; no
  simulator, device, or transferred-page execution.
- Official D3d remains selected at 29,470 B.
- Exact result:
  `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step4-common-floor/d3/materializer-compression-probe/RESULTS.md`
- Machine evidence:
  `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step4-common-floor/d3/materializer-compression-probe/results/machine_closure.json`
- Final machine-readable result SHA-256:
  `451d7e89e5939f8ad82eb28e9779db2daa0bd6267e7ce661cf93c48af4dd8f81`.

## Next action

Do not adopt the descriptor table. Keep official D3d for Step 5 unless the
60-B header-guard candidate is promoted through an explicit arena-freshness
contract, regenerated official artifacts, and independent review.
