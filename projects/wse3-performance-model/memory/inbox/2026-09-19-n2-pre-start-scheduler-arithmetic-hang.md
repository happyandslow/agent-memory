# N2 pipeline hangs before START while its mini simulator passes — 2026-09-19

**Project:** wse3-performance-model
**Author:** codex
**Status:** captured

## What happened / finding

- Tall layout-C N2/W2 can remain at A1 tick=0/starts=0 because scheduler
  arithmetic executes before the START gate. Result-dependent hardware markers
  locate the stop before that arithmetic completes, in both mini and original
  full geometry. A one-PE scheduler-only program reproduces it without START,
  feedback, collectives, or model compute. Simulation passes.
- The implicated runtime signed-i16 division/remainder path links
  `__divhi3`/`__udivhi3`. Their loaded bytes match the actual worker ELF; the
  precise instruction-level fault is unknown. Do not label this a universal
  divide bug or an established credit-ring deadlock.
- Replacing only the N2/L2 scheduler with equivalent shifts/masks restores
  the tiny case and complete mini/full CS-3 cases. Independent CPU references
  match all 10,560/84,480 values exactly (33 steps, two layers; full
  width/head128, dimension2560, prefill1280, capacity8192). A separate patch
  rejects piped layer counts other than two at compile time. Production and
  staging were not changed.
- Historical comparison verifies all nine preserved pre-slot files against
  their hashes and exact patch. Both versions calculate frame indices before
  START; the regression introduces a runtime cohort divisor instead of the
  old constant layer divisor. Two hold arrays already existed, and the serial
  mini ELF already retains X_hold. This identifies the source trigger, not
  the unresolved instruction-level failure mechanism.
- This corrects the prior handoff's practical assumptions: small hardware
  reproduction exists, and worker-native HAL debugging exists. Full native
  core dump attached but yielded no usable contents within 120 seconds;
  selected `HalDevice2.read(Rectangle, word_addr, word_count)` live SRAM reads
  were validated with an exact magic and advancing counter. Derive physical
  coordinates and addresses from that worker's own viz/params/listing/ELFs.

## Implications / next actions

- For a pre-START hang, instrument result-dependent markers before blaming
  transport. Inspect emitted ordering: naive before/after counters were moved
  around shared arithmetic by the compiler. Empty output plus timeout is not
  an observed program counter.
- Two early job cancellations used unproven shared-account timing attribution;
  those observations were retracted. Require exact launcher-owned job IDs for
  cancellation. Queue deltas do not prove ownership.
- Use the isolated guarded patch for review; instruction-level diagnosis and
  wider configuration validation remain separate work.

## Pointers

- `/home/lexu/wse3-performance-model/demo/fused-block/xz-staircase/investigation-2026-09-18-debug2/DIAGNOSIS.md`
- Same directory: `sim/final-fix/ORIGINAL_TO_FINAL_FIX.patch`,
  `observability/FINAL_DIAGNOSTIC_EVIDENCE.md`, `device/REPORT.md`.
- Same directory: `history-comparison/HISTORICAL_CAUSE.md` (source provenance
  and corrected consultation with Claude session `4b-mini-ppl-debug`).
- Supersedes relevant capability/localization assumptions in
  `2026-09-18-pipe-slots2-deadlock-handoff.md`; does not rewrite that capture.
