# The N=2 fine-grained pipe hang was NOT a deadlock — it's a runtime-divisor scheduler helper that stalls on device; shifts/masks fix it — 2026-09-18 (CORRECTED 2026-09-19)

**Project:** wse3-performance-model
**Author:** claude
**Status:** captured — RESOLVED + independently reproduced. (This note originally
concluded "deadlock, mechanism unpinned, dump-core blocked" — that was WRONG and
is corrected below.)

## Situation this applies to

You enabled the tall layout-C decoder's fine-grained pipeline (`--pipe-slots 2
--feedback --layers 2`, N=2 position-slot cohort over the A1/A2/A3 feedback ring,
`demo/fused-block/xz-staircase/`) and it hangs on CS-3: compiles, loads, starts
executing, then no progress → bounded.py 900s deadline → exit 124. Serial
(`--pipe-slots 1`) is byte-correct (TIMING 68,151). The mini oracle passes
bit-identical in **simulation**.

## Corrected finding (the earlier "deadlock" was wrong)

**Root cause = the N=2 scheduler's runtime-divisor arithmetic, NOT a
synchronization/credit deadlock.** `pipe_a1` computes
`frame_slot/frame_layer/frame_token` before the START gate; those divide/
remainder by the **runtime** `cohort_size()` (2, or 1 at the odd tail), which
links `__divhi3`/`__udivhi3` into the A1 ELF. The PE stalls at that first
scheduler arithmetic on device, **before any compute**. Decisive evidence: a
single PE with NO START/credit/collective/compute reproduces the hang at the
first arithmetic; the same arithmetic PASSES in simulation. The old serial
scheduler used `tick % layer_banks` / `tick / layer_banks` with a **compile-time
constant** divisor (`layer_banks=2`) — no helper — which is why serial never hung.

**Fix (debug session's):** express the N2/L2 schedule as shifts/masks
(`batch=tick>>2`, `pos=tick&3`, `layer=pos>>1`, `slot=pos&1`, odd tail → slot 0,
layer=pos), removing the runtime-division helper; buffers/START/ACK/credit/
collective all retained.

**Independently reproduced on CS-3 (2026-09-19, this session):** original
`tall_stage.csl` SHA `28ed82f` → exit 124; fixed SHA `40341434` → exit 0, output
`actual.npy` SHA-256 `f84a4426…` **byte-identical to the debug session's CPU
operation-order-oracle-verified output** (84,480 values). Fix promoted to the
production tree, gated behind `--pipe-slots 2`; serial unchanged.

## What was wrong in the original capture (retracted)

- "It's a deadlock / the credit ring closing edge is unpinned" — WRONG; no
  deadlock (a single PE with no comm hangs; the fix completes bit-identical).
- "dump-core is a dead end / device has no dump/read capability" — WRONG; native
  HAL SRAM live reads work (validated with magic + advancing counter). Only the
  *full* core dump didn't yield usable contents in 120s.
- "hang needs 128-wide; get 128-wide into simfab" — WRONG framing; the failure is
  **sim-vs-device**, not scale: PASSES in sim at every scale, FAILS on device even
  at mini. Sim will never reproduce it.
- **Still valid:** the refutation of the naive credit cycle (sync was never the
  cause — corroborated); the per-stage timing / ~2.5–3.7× ceiling (unrelated to
  this bug).

## Why it matters / how to apply

The general lesson: a **runtime (non-comptime) integer divisor in a hot CSL path
links `__divhi3`/`__udivhi3` and can stall on WSE-3 hardware while passing in
simulation** — a sim-vs-device divergence, not a scale or synchronization issue.
When a piped/multi-slot scheduler replaces a comptime-constant divisor with a
runtime one (here to support an odd final cohort), prefer shifts/masks/conditionals
for power-of-two or tiny divisors. Debug by isolating the arithmetic into a
single-PE reproducer on **device** (not sim). Mechanism (why the helper doesn't
return) is still unproven — next experiment: read the stalled PE's live PC.

## Pointers

- Corrected handoff: `docs/reports/2026-09-18-pipe-slots2-deadlock-investigation-handoff.md` (top banner = RESOLVED).
- Debug session: `demo/fused-block/xz-staircase/investigation-2026-09-18-debug2/` — `DIAGNOSIS.md`, `history-comparison/{HISTORICAL_CAUSE,COMPILE_PATH_AUDIT}.md`, `sim/final-fix/{ORIGINAL_TO_FINAL_FIX.patch,REPORT.md}`, device SRAM/live-read tooling.
- Fix in production: `package/tall/src/tall_stage.csl` SHA `40341434` (frame helpers shifts/masks + `@comptime_assert(!piped or layer_banks==2)`).
- Related: [[2026-09-17-tall-fine-grained-pipeline-and-per-stage-vs-context]] (per-stage timing, ~2.5–3.7× ceiling), `simfab-stall-diagnosis-recipe`, `cerebras-debugging` skill (sim-vs-device, artifact SHA discipline).
