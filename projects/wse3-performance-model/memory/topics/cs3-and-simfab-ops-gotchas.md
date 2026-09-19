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

## Updates — 2026-09-19: a CS-3 hang can be inspected through worker-native HAL

When the host receives zero output and the simulator passes, do not conclude
that device state is inaccessible because public `SdkRuntime.dump_core` is
simulator-only or the login shell lacks debug tools. The actual CS-3 appliance
worker exposed native HAL, `Target`, `csdb`, and `sdk_debug_shell`.

- **Full dump:** the tested `Target.save_core(prefix)` wrapper omitted a required
  bool and raised TypeError. Native `target.hal_device().core_dump(prefix, True)`
  attached, but its fabric-wide scan produced no usable core contents in the
  120-second bound. The bool is `skip_teardown_reg`; it is not a pause switch.
  This is a bounded negative result, not proof that hardware core dumps cannot
  exist or that every future binding has the wrapper defect.
- **Usable method:** `instantiateDevice(cmaddr).read(Rectangle(x,y,1,1),
  word_address, word_count)` returned live u16 SRAM words. Validate it first on
  a retained nonzero magic and an advancing counter. The tested API uses
  16-bit word addresses/counts; convert aligned ELF byte address/size by `/2`.
- **Artifact join:** use that run's actual worker `sim.viz`, `sim.params`,
  `sim.lst`, and ELF hashes to join role -> physical PE -> compile key -> symbol.
  Local ELF addresses and same-named compile keys are not interchangeable with
  device artifacts. Fail on wrong geometry, missing required fields, empty
  reads, or read errors; preserve raw words and actual sample timestamps.
- **Interpretation:** snapshot existing counters before adding probes. New
  post-call markers must depend on the computed result, and emitted ordering
  must be checked; the compiler reordered naive counters and merged helpers.
  A stable marker frontier is not a live PC or proof of an infinite loop.
  Sequential field/PE reads are not an atomic whole-wafer snapshot.
- **Avoid failed paths:** `debugcommon.read_memory/read_registers` with an empty
  checkpoint prefix took an offline path; zero process exit masked logged
  errors. The earlier `hal-live-read-sanity/` is that failed attempt; the direct
  reader is `hal-live-direct-read-sanity/`, validated by its R2 device result.
- **Preserve evidence:** atomically save each PE's records, archive compile/map
  artifacts before execution, and download in failure paths. `runtime.stop()`
  can hang after successful capture; use fresh-run status and a separate bounded
  cleanup grace. The validated harness records intentional diagnostic exit125
  after its own child termination, distinct from a successful kernel result.
  Cluster cancellation requires a launcher-proven job ID, never account-wide
  timing/queue-delta attribution.

The reusable procedure is in the canonical
[cerebras-debugging skill](/home/lexu/claude-skills/cerebras-debugging/SKILL.md)
and its [live SRAM/core-dump reference](/home/lexu/claude-skills/cerebras-debugging/references/cs3-live-sram-and-core-dump.md).
Evidence: `/home/lexu/wse3-performance-model/demo/fused-block/xz-staircase/investigation-2026-09-18-debug2/observability/FINAL_DIAGNOSTIC_EVIDENCE.md`;
actual full-layout capture: `device/step-frontier-full-result/` under that
investigation root (69 records, 981 values, zero read errors). This method
located a pre-START arithmetic failure; no live PC/register capture was validated.
