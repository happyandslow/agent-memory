# WaferLLM function container M5R-3 final-link REVISE — 2026-08-17

**Project:** WaferEngine
**Author:** codex
**Status:** captured

## What happened / finding

- Situation: M5R-0～2 had established a per-symbol receiver ABI and entry-local
  DSD source shape, but the full Attention/FFN pages still needed a real
  receiver composition, fixed addresses, final entry offsets, and executable
  closure proof before they could be admitted to one shared slot.
- M5R-3 built a canonical receiver data arena at `0x4000`: 9,338 bytes, 32
  four-byte-aligned regions including `alpha`.  The 16-word `page_control` is a
  separate real object at `0x7000`.  Page-linked audit images contain only the
  phase-consumer fixed-address stand-ins and compare them with receiver
  arena-base plus manifest offset; the design does not use a retention
  scaffold, alias table, self-assignment, gated store, or shadow phase compute.
- Both policies linked Attention and FFN at a common slot address `0x1a00`.
  Policy P has a 4,096-byte slot with 4,088-byte Attention and 2,112-byte FFN
  pages.  Policy R has a 3,840-byte slot with 3,796-byte Attention and
  1,876-byte FFN pages, plus a live five-word ABI at `0x7800` (10 bytes) and a
  fixed resident vecmat section at `0x7a00` (196 bytes).  Receiver low-user
  high-water is `0x7020` for P and `0x7ac4` for R.  These are static complete-
  image/link figures, not dynamic net savings.
- Entry-offset encoding needs a fixed-point relink.  P/R Attention converged in
  one iteration; P/R FFN converged in two.  Every nonterminal final source
  writes the next final-linked entry offset to `page_control[6]`; A7/F3b write
  zero.
- Admission still fails: across 182 canonical page-specialization records, a
  `.m4_page` `____divhf3__retaddr` symbol targets a 168-byte `__divhf3` FUNC in
  slot-external `.text`.  Empty relocation tables do not remove this explicit
  code escape.  No WSE-aware disassembler was available, so the remaining
  call/branch/back-edge closure also stays fail-closed.
- Final conclusion is `REVISE_EXTERNAL_CODE_ESCAPE`, evidence grade `NONE`.
  The six memory maps are exact static final-ELF overlays; they do not prove a
  loader transfer, page execution, numerical correctness, latency, or Phase 2.
- A fresh Fable 5 review passed the evidence tree while affirming the REVISE/
  NONE stop.  It found that `__divhf3` is composition-local, not a common
  receiver address: 4,752 in Attention links and 4,604 in FFN links.  It also
  identified follow-up audit hygiene: remove or pin FFN `alpha` instead of
  relying on dead stripping; align the arena manifest text with the enforced
  four-byte padding; re-assert final receiver/slot non-overlap; validate the
  five-word R ABI per call site; and compactly report P per-object equality and
  payload-variant counts.

## Implications / next actions

- [ ] Stay in Phase 1 Step 3 and choose an auditable `__divhf3` closure:
  section-place the compiler helper inside each page, or explicitly approve and
  address-match it as a resident service.  Re-run all P/R final links afterward.
- [ ] Obtain an authoritative WSE-aware disassembly path and prove every
  call/branch/back-edge target before assigning Grade E.
- [ ] Treat `__divhf3` as a must-fix address-contract problem: the current
  Attention and FFN link addresses differ and neither has been proven equal to
  a receiver target.
- [ ] Keep U04 (production-effective RoPE odd-lane offset 0) unresolved; do not
  silently mix its semantic repair into code-closure work.
- [ ] Do not begin loader/runtime, transferred-page correctness, simulator,
  CS-3, or Phase 2 while M5R-3 remains REVISE.

## Pointers

- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/STEP3_TRACKING.zh-CN.md`
- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step3-page-regions/m5r3-final-link/README.md`
- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step3-page-regions/m5r3-final-link/results/m5r3_report/`
- Scratch raw evidence: `/home/lexu/WaferEngine-staging/.m5r3_final_link/`

## Division-blocker follow-up after DIV-4 (2026-08-18)

The original external `__divhf3` blocker is superseded at the named-target
level. DIV-4 production-shaped final relinks have empty page relocation tables
and zero named `.m4_page -> __divhf3` targets for Routes A/B/C2. The division
sub-verdict is now `PASS_DIVISION_STATIC_NAMED_TARGET_GATES`, Grade E.

The overall Step 3 verdict remains `REVISE`, not PASS: U04 RoPE odd-DSD
semantics remain unresolved, and no WSE-aware disassembler proves every unnamed
call/branch/back-edge. Route A is the default, Route B the fail-closed fallback,
and C1/C2 are rejected. See
`memory/inbox/2026-08-18-waferllm-division-closure-div4-final-comparison.md`.

## Route-A/P and U04 source checkpoint (2026-08-18)

The active Step-3 source policy is now frozen to Route A + P. DIV-4 measured
P at 20,524 bytes complete receiver allocation versus R at 20,644 bytes: R
saves 256 slot bytes but adds 376 permanent bytes, so it loses 120 bytes in
the complete static receiver. Route B + P remains the fail-closed division
fallback.

U04 is no longer silently deferred. The M5R-3 composition generator repairs
both fresh A2 odd-lane RoPE DSD constructors from offset 0 to offset 1; the K
path then adds `bsz*dim_p_pe`, and per-batch increments preserve the +1 odd
component. Production Decode is unchanged. Deterministic source generation and
validation pass at Grade S, including exact Route-A anchor counts and hashes of
the DIV-4 decision inputs.

This is not a final-linked result. Historical M5R-3 and DIV-4 ELFs still encode
the old U04 source and must remain immutable. The canonical M5 gate stays open
until Route-A/P+U04-repaired source is relinked, receiver/link audit hygiene is
closed, and a WSE-aware whole-page control-flow audit succeeds.
