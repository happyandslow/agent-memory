# WaferLLM function-container M5 stopped at REVISE

Date: 2026-08-16

Project: WaferEngine / WaferLLM MeshJIT Decode

Status: drained 2026-08-19 into `memory/topics/meshjit-code-relocation.md` and `plan.md`

## Durable conclusion

Phase 1 Step 3 M5 did not establish a final address-matched Attention/FFN
shared slot. The audit stopped fail-closed before final `SLOT_ADDR`, R-policy
composition, receiver-floor accounting, runtime work, or Phase 2.

Two SDK 2.10 provisional P (page-private vecmat) links succeeded at
`.m4_page = 0x9000`. Each phase produced 31 linked executable artifacts. The
nominal page-independent receiver-retention sections were uniform within each
phase but differed between Attention and FFN:

| Section | Attention | FFN |
| --- | ---: | ---: |
| `.m5_pinned_data` | 8,944 B | 9,176 B |
| `.m5_data_retention` | 136 B | 116 B |
| `.m5_pinned_state_p` | 62 B | 46 B |
| `.m5_state_retention` | 80 B | 64 B |

This falsified five source-level ownership/retention mechanisms for this
compiler flow: section anchors, exported pointer-alias tables, direct array
exports, exported noinline self-assignments, and a mutable-gate observable
store scaffold. The compiler still specialized/pruned the retained data/state
closure by page. None of these scaffolds may be treated as a production
receiver ABI or used for `net_free` economics.

There are two independent closure blockers. Every provisional P ELF contains
one 168-byte hidden `__divhf3` function outside `.m4_page`; symbol presence and
placement are proven, but the page-to-helper call edge is deliberately not
claimed without WSE disassembly. The available host `llvm-objdump` rejects the
ELFs as `elf64-unknown`, and no usable SDK `elf2lst` path was available, so
call/branch/back-edge closure cannot pass.

The final deterministic audit status is `REVISE`; four final page labels and
two receiver labels are all `BLOCKED`, evidence grade is `none`, and economics
is `unmeasured`. Fable 5 first found address, reproduction, and latent validator
bugs; after fixes, a targeted read-only re-review returned PASS.

## Retry gate

Before retrying M5:

1. define a real page-independent M1/M3 receiver-state realization rather than
   another source-level retention trick;
2. place compiler helpers such as `__divhf3` inside the page closure or make an
   explicit, address-matched resident-helper contract and account its floor;
3. obtain a WSE-aware disassembly/control-flow proof before approving external
   targets, branches, or backedges.

Do not infer a final slot size, receiver SRAM saving, execution correctness, or
Phase 2 admission from the provisional P links.

## Authoritative evidence

- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/STEP3_TRACKING.zh-CN.md`
- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step3-page-regions/m5/README.md`
- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step3-page-regions/m5/results/m5_fail_closed_revise.json`
- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step3-page-regions/m5/results/m5_disassembler_attempts.json`
- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step3-page-regions/m5/REVIEW_RESPONSE_FABLE5.md`

Evidence hashes at capture:

- materialized inventory: `1e20c612c61a9cd0079aff0776357d3accfd337f85a28ce2ed2abf2e30d488fb`
- fail-closed report: `32267a8fe517344f847a59d8d28eac25488baab2cd2a7ce1c08b3703b10f3abb`
- final blocked audit: `679b57b587d677e095b73fc3af6c0825ba0dcb96731538342fb1519eff0d7ac6`
- tracking document: `92614130c4d5e3ecebfdde258b12eecd3f01093492c93fa20a66a79edff0bf35`
