# WaferLLM Attention/FFN shared-slot: M6, Step 4, and bsz=2 closeout

Date: 2026-08-20

## Durable decisions

- Phase-1 Step 3 is canonically closed at PASS / Grade E. The active capacity
  policy remains division Route A plus private-link vecmat Policy P. Route B/P
  is the deterministic division fallback; resident vecmat Policy R remains an
  unmeasured performance alternative and costs 120 B more complete receiver
  SRAM at bsz=1.
- The M6 aggregate is authoritative over older immutable pre-machine and
  pre-review envelopes. Those older reports correctly retain REVISE/PENDING;
  they must not be edited in place.
- M6 now parses and hash-binds 10 historical failure/review sources into 87
  explicit source entries. Every entry has exactly one reviewed disposition;
  source drift, entry-list drift, duplicate/missing mapping, or an `ACTIVE`
  disposition fails closed. A fresh independent re-review closed all five M6,
  Step-4, tracking, helper-accounting, and bsz=2 provenance findings.
- Phase-1 Step 4 D0-D3 is canonically closed at Grade E for bsz=1:
  D0=20,060 B, D1=20,426 B, D2=20,700 B, D3=29,470 B. The official D3 remains
  `D3d_terminal_quiescence`; the 29,410-B sparse materializer probe is not
  adopted.
- bsz=2 cannot reuse bsz=1 page roots, continuation offsets, slot capacity, or
  loader/invoke placement. Its active Route-A/P slot is 5,120 B at
  `[0x1a00,0x2e00)`, with loader at 0x2e00 and invoke at 0x2f00.
- bsz=2 pre-profile capacity is already negative: B=27,180 B and D3d=30,998 B,
  so `B-D3d=-3,818 B`. With the implementation otherwise unchanged, Step 5
  needs at least 3,819 B of additional recovery for strictly positive net free;
  profile reservation itself will add resident cost. Step 5 must still measure
  both bsz=1 and bsz=2 profile ownership rather than copying bsz=1 bytes.

## Why the D3 functions are large

- `d3_execute_operation` is 952 B / 238 WSE instructions. Its own expanded
  11-key dispatch and guards consume 804 B; the seven unique communication
  helpers it calls are separate symbols totaling 3,116 B and are not included
  in that 952 B.
- `d3_invoke_bound_entry` is 756 B / 189 instructions. The 13-entry
  page/entry/profile allow-list consumes 440 B; ten explicit command-arena
  clear calls consume 116 B. `noinline` prevents body duplication into callers
  but does not compress either function's own comparisons and branches.
- The earlier descriptor-table compression was worse: +920 B complete SRAM and
  a slot-external memcpy closure. There is no hidden large table in the
  canonical implementation; page control is 32 B and command arena is 20 B.

## bsz=2 measured sensitivity

- B=27,180 B; A_both=15,322 B; joint removable=11,858 B (+1,426 B vs bsz=1).
- Attention page=4,916 B (+728 B); FFN page=2,424 B (+148 B); slot=5,120 B
  (+768 B); static receiver=22,044 B (+1,520 B).
- D0=21,580 B; D2c=22,220 B; D3d=30,998 B. D3 runtime cost over D2 grows by
  only 8 B, so most sensitivity comes from batch-shaped data/page ownership.
- Route-A/P page machine audit passes; D3d passes WSE machine closure for all
  36 specializations. Evidence remains static Grade E and does not establish
  transferred-page or numerical correctness.

## Evidence

- M6: `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step3-page-regions/m6-canonical-closeout/`
- Step 4 root summary:
  `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step4-common-floor/STEP4_COMPLETION.zh-CN.md`
- Step 4 machine-readable summary:
  `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step4-common-floor/results/step4_common_floor_summary.json`
- bsz=2 compact package:
  `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/bsz2-sensitivity/`
- M6 disposition contract:
  `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step3-page-regions/m6-canonical-closeout/manifests/failure_dispositions.json`
- D3 function source:
  `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step4-common-floor/d3/generated/D3d_terminal_quiescence/src/decode.csl`
- D3 machine audit:
  `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step4-common-floor/d3/results/d3_machine_runtime_audit.json`

## Evidence limits

This closeout proves linked ownership, complete-image SRAM, fixed placement,
specialization inventory, and WSE machine-control-flow closure. It does not
prove loader/holder runtime, transferred-page execution, numerical/model
correctness, queue drain, global quiescence, latency, or dynamic net saving.

The requested pre-Step-5 Git checkpoint is intentionally compact: source,
generators, manifests, command/log records, hash inventories, extracts, and
reports are staged. Roughly 1.4 GB of reproducible Step-4 raw `out` ELF trees
remain as worktree evidence and are not staged; no commit or push was made.
