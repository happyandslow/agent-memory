# CS-3 and simfab operational gotchas

- `cs3-run` does not forward heredoc/stdin into nested SSH commands; write a remote script or pass a command string.
- Variables intended for `cs_python` in Singularity need `SINGULARITYENV_` prefixes; `cs3-tmux ensure` needs a tty in non-interactive use.
- simfab 0-byte receive / kernel-stall aborts can be host-service stalls (~90 s) rather than kernel bugs; validate by replaying real frames or keeping the host servicing the runtime.

## 2026-09-14 update — CSL/SDK 2.10 gotchas from the fused-block microbenches

- `@fmachs` multiplies at **f32 precision on widened f16 operands**; the doc's
  "16-bit multiply, 32-bit add" wording is misleading. A host reference that
  multiplies in fp16 mismatches every element in the last 2–3 digits — widen
  both operands to f32 before multiplying or a parity checker reports false
  failures.
- **Input queues 0 and 1 are reserved by the memcpy H2D system**
  (`memcpyh2d.csl:584` initialises IQ0): user colours on IQ0/1 fail with
  "initialization for this queue has already been set". Use IQ2+.
- `memcpy/get_params.csl`'s `get_params(px)` keys `first_pe`/`last_pe` off the
  **physical x-coordinate**; passing a row-major linear index only coincides on
  row 0 — every later row gets a silently broken port and the simulator dies
  with a bare SIGSEGV, zero compile-time signal.
- The project's fixed `--max-inlined-iterations=8` is tripped by the `<time>`
  library's TSC reset loop; for same-PE deltas write the control register
  directly (no reset needed).
- A fork of an agent inherits the parent's context and can believe it is the
  parent "waiting on a fork" that will never report to it; it then discards
  messages carrying its own name. Symptom: repeated idle notifications saying
  "still waiting on the fork" with zero tool uses. Fix: message it explicitly —
  "you are the fork; do the work directly" — and never let a non-load-bearing
  fork appear in status lines.
