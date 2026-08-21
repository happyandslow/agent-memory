# WaferLLM function-container Step 3 static admission review PASS — 2026-08-18

**Project:** WaferEngine  
**Author:** codex  
**Status:** drained 2026-08-21 into `memory/topics/meshjit-code-relocation.md` and `plan.md`

## What happened / finding

- Situation: an Attention/FFN shared-slot final-link audit can appear internally
  consistent while its compact admission layer still accepts a missing
  specialization, post-build source drift, stale PASS, source/ELF splice,
  duplicate family row, arbitrary compile argv, incomplete source manifest, or
  nested machine-audit failure.
- The final v4 evidence uses Route A + P as the capacity-active policy and Route
  B + P as the fail-closed math fallback. P complete receiver allocation is
  20,524 B; R is 20,644 B because its 256 B smaller slot is outweighed by a
  376 B larger permanent floor. U04 odd-lane DSD constructors are repaired to
  offset 1 in page composition without changing production Decode.
- Both Route A/B v4 roots were rebuilt after the final provenance schema change.
  Each route has 182 page-bearing ELFs and 30 receiver-R ELFs. SDK `elf2am`
  machine-control-flow audit reports complete instruction coverage, zero
  failures/rejections, page-local direct call/branch/back-edge closure, and only
  the approved R fixed escape to resident vecmat at `0x7a08`.
- Admission reconstructs exact canonical `cslc` argv and section placement from
  the frozen builder/final slot, requires the recorded source map to equal the
  complete compiled source tree, verifies the actual compile-log hash, preserves
  specialization multiplicity, and independently checks aggregate, family,
  representative, and per-ELF verdicts.
- Twenty-nine positive/mutation tests pass. A fresh sixth independent reviewer
  with no conversation context additionally reconstructed all eight canonical
  command/source/log bindings and tested placement-only and nested-status-only
  mutations. Verdict: `PASS — no actionable findings remain`.

## Implications / next actions

- [x] Treat Phase 1 Step 3 static admission as review-PASS / Grade E; the v4
  candidate has been materialized into WaferLLM after user approval.
- [ ] Start M6 only on explicit user direction; do not infer authorization for
  loader/runtime, simulator/device, Step 4, or Phase 2.
- [ ] Preserve residual limits: no transferred-page execution, numerical/model
  correctness, loader/continuation-runtime correctness, latency, or dynamic
  SRAM-saving evidence. Static `jmp r15` cannot identify a unique dynamic
  return target.
- [ ] Reuse the fail-closed evidence pattern in later pageability work: validate
  multiplicity before set conversion, reconstruct commands rather than trusting
  records, compare complete source trees, atomically replace stale PASS on tool
  failure, and audit every nested verdict layer independently.

## Pointers

- Candidate: `/home/lexu/WaferEngine-staging/.m5r3_step3_completion/`
- Raw v4 A: `/home/lexu/WaferEngine-staging/.m5r3_step3_completion_runs/route_A_v4/`
- Raw v4 B: `/home/lexu/WaferEngine-staging/.m5r3_step3_completion_runs/route_B_v4/`
- Review history: `.m5r3_step3_completion/INDEPENDENT_REVIEW_HISTORY.md`
- Target tracking:
  `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/STEP3_TRACKING.zh-CN.md`
