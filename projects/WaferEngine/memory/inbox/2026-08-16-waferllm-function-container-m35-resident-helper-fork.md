# WaferLLM function-container M3.5 symmetric resident-helper fork — 2026-08-16

**Project:** WaferEngine
**Author:** codex
**Status:** corrected capture; supersedes the earlier asymmetric M3.5 note

## What happened / finding

- The first M3.5 accounting was invalid. It compared a page-only P probe with
  an R receiver and reported `188 - 1,120 = -932 B`; P had no matched
  receiver/host/slot-admission image. That result is superseded and must not be
  used.
- The replacement builds four counterparts from frozen SDK-2.10 `A_both`:
  `in_page/page`, `in_page/receiver+host`, `receiver_side/page`, and
  `receiver_side/receiver+host`. Both use the same five-word ABI, slot address,
  invoke wrapper, host-H2D loader contract, production config, and comparable
  final-link conditions.
- The stable cross-image ABI is `[5]u16`: X/Q/W addresses, Kt, and Nt. Each page
  binds to its paired receiver's specialization-uniform natural buffer
  addresses. DSD/DSR state is helper-local; the invoke wrapper reserves required
  DSR kinds with valid extent-1 resident descriptors rather than reading the
  initially zero ABI.
- Static Grade-E final-link result: P/R page and actual slot sizes are 228/40 B.
  Complete receiver high-water is `D_P=16,868 B`, `D_R=16,680 B`; therefore the
  authoritative actual-sized delta is `SRAM(D_P)-SRAM(D_R)=+188 B`, favoring
  resident-side vecmat for this minimal probe.
- Equal-slot control gives both receivers a 228-B slot. Both high-water values
  are 16,868 B. R links 208 B more allocated sections and consumes 208 B less
  fixed gap, so its incremental non-slot complete-image floor is 0 B in this
  placement. Linked bytes and gap bytes are explanatory components, not extra
  deltas to subtract.
- ABI is fixed at `0x3e00/10 B`, pages at `0x4100`; P/R entry offsets are 196/0
  B. Resident vecmat is `0x3f00/188 B`, callback `0x3fc0/8 B`. All 28 P receiver
  specializations lack vecmat/callback symbols and resident helper sections;
  all final receiver specializations retain the fixed ABI and have no final
  relocations.
- The host accepts only build-generated paired bundles. It verifies payload
  SHA-256 and receiver `out.json` values for P, slot words/address, and entry
  offset, then loads all 256x256 PEs. This corrected an independent-review FAIL
  where the first host defaulted to 1x1 and trusted caller-supplied slot size.
- Targeted independent re-review passed after these fixes. Claude Code attempts
  ended with execution errors and produced no verdict; do not cite a Claude
  PASS for this replacement.
- Communication placement was not re-decided by this symmetric vecmat gate.
  M2 resident-command communication remains the M4 baseline; communication
  fabric/queue/route/collective lifecycle equivalence is unresolved.

## Implications / next actions

- [ ] Start M4 only after user acceptance. Generate P/private and
  R/resident-direct full Attention/FFN candidates from one production-derived,
  hash-guarded generator; do not maintain two handwritten algorithms.
- [ ] M5 decides vecmat placement using the complete full-page
  `max(attention, ffn)` slot and complete receiver images. The M3.5 `+188 B`
  result is a minimal-probe outcome, not final `net_free`.
- [ ] Keep communication on the approved M2 command/yield path in M4.
- [ ] Transferred-page execution, return/control flow, and numeric correctness
  remain later runtime gates; M3.5 claims Grade E only.

## Pointers

- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/STEP3_TRACKING.zh-CN.md`
- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step3-page-regions/m35/README.md`
- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step3-page-regions/m35/M3_5_REVIEW.md`
- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step3-page-regions/m35/results/complete_image_economics.json`
- `/home/lexu/WaferLLM/MeshJit-Decode/FUNCTION_CONTAINER_DESIGN.md`
