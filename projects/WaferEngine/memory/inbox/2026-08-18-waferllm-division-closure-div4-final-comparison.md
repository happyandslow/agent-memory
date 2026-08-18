# WaferLLM DIV-4 production-shaped division-closure comparison

Status: captured

Situation: Attention and FFN share one executable slot, and division closure
can use SDK `<math>` lowering (Route A), page-private SDK-derived helpers
(Route B), or fixed-address resident SDK-derived helpers (Route C2).  Isolated
helper sizes are insufficient because slot alignment and the complete receiver
floor decide SRAM economics.

## Durable result

SDK 2.10 production-shaped final relinks covered Route A/B/C2 across P/R x
Attention/FFN (12 page families) and six matched receiver images.  Static named
target gates pass at evidence Grade E:

| Route | P slot | R slot | Complete receiver vs B |
|---|---:|---:|---:|
| A | 4,352 B | 4,096 B | equal |
| B | 4,352 B | 4,096 B | baseline |
| C2 | 4,096 B | 3,840 B | P +168 B; R +184 B |

Route A's Attention payload is 48 B smaller than B and its FFN payload is 20 B
larger, but Attention determines the slot and 256-byte alignment makes A and B
identical in receiver SRAM.  Route A is the provisional preference because its
source integration is simplest; Route B is the explicit source/section
ownership fallback.

The route policy is now frozen into the prior milestones:

- M1/M2 add no division ABI or yielding change.
- M3 classifies division math as page-local and admits no resident-math
  component.
- M4 generates Route A by default and retains deterministic Route B generation
  as a fail-closed fallback; the two paths must never coexist in one image.
- M5/M5R-3 must audit every emitted specialization and switch to Route B or
  fail closed if Route-A lowering, hashes, relocations, or named targets drift.
- M6 reports the selected route and evidence limits without claiming runtime
  correctness.
- Phase 2 must compare Route A numerically against the frozen slash expressions
  for RMSNorm, softmax, and SiLU before page correctness can pass.

C1 (compiler-local `__divhf3` as a resident ABI) is rejected because its
matching address was emergent and moved with unrelated `.text`.  C2 is rejected
for the complete-receiver economics below.  This closes the division
**named-target** subproblem only; the overall Step 3 verdict remains `REVISE`.

C2 removes 332 B from each page and reduces the aligned slot by 256 B, but its
permanent receiver floor excluding the slot grows by 424 B (P) / 440 B (R).
It is therefore uneconomic for this two-page container.

All final page relocation tables are empty and there are zero named
`.m4_page -> __divhf3` return sites.  Route A has no named external page target
at symbol-table level; Route B helpers are in `.m4_page`; C2's approved fixed
helpers are uniform at `invsqrt@0x2a00` (148 B) and `inv@0x2c00` (184 B).
The inherited R resident vecmat target remains `0x7a08`.

Actual page-bearing deduplicated specialization counts are 52/38/53/39 for
P-Attention/P-FFN/R-Attention/R-FFN, and 56/42/57/43 for C2.  The earlier
25-image assumption must not be used for production evidence.

## Limits and next gate

Verdict: `PASS_DIVISION_STATIC_NAMED_TARGET_GATES`, not whole-page correctness.
U04 RoPE odd-DSD offset=0 remains unresolved.  There is no WSE-aware
disassembly, numerical equivalence, loader/transfer/invoke, simulator/device,
latency, or dynamic net-saving evidence.  Stop before M6/runtime/Phase 2.

The post-DIV Step-3 audit adds these active gates:

- freeze vecmat placement: P is the current capacity-preferred candidate because
  its complete receiver allocation is 120 B lower than R for both math Routes
  A and B; R remains only a smaller-page/performance alternative;
- resolve U04 or explicitly reclassify it as a later correctness gate;
- align the arena manifest with the actual four-byte placement, add explicit
  final receiver/slot non-overlap checks, and validate the R five-word ABI at
  each of the nine call sites;
- regenerate Route-A active and Route-B fallback pages, then obtain WSE-aware
  call/branch/back-edge evidence;
- obtain one fresh final review and only then produce M6.

Evidence:

- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step3-page-regions/m5r3-division-closure-probe/div4/RESULTS.md`
- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step3-page-regions/m5r3-division-closure-probe/div4/results/div4_comparison.json`
- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step3-page-regions/m5r3-division-closure-probe/div4/manifests/division_route_decision.json`
- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step3-page-regions/m5r3-division-closure-probe/div4/MILESTONE_INTEGRATION.md`
- `/home/lexu/WaferLLM/MeshJit-Decode/FUNCTION_CONTAINER_DESIGN.md`
- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/STEP3_TRACKING.zh-CN.md`
