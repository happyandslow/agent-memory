# runtime.load() on-chip artifact upload cost (worker-local, directly timed) — 2026-08-06

**Project:** WaferEngine-staging
**Author:** claude
**Status:** drained   <!-- drained 2026-08-06 into topic m2-s0-baseline-and-timer-provenance.md § Updates -->

## Situation this applies to

You are pricing a pdSeparate device cycle, or reasoning about runtime code
loading (MeshJIT / code-as-resource), and need the cost of getting the compiled
artifact onto the wafer *from the worker node* — i.e. after the 6.6 GB
gateway→worker rsync/staging, the `runtime.load()` step itself. The M2-S0
timer-provenance note records the ~416 s "untimed bracket" but does NOT record
this number, and it is easy to conflate `runtime.load()` (the ELF→wafer upload)
with `SdkRuntime(...)` construction ("attach"). They are different.

## Finding

- `runtime.load()` **is directly timed** — `perf_counter` wraps the exact call
  and stores `load_s` (`launch_prefill.py:1939-1943`, `launch_decode.py:4066-4067`;
  printed "runtime.load took Xs", comment "ELF -> wafer program+weight load").
  It is NOT a bracket/subtraction estimate.
- **Measured `load_s` (real CS-3, worker node, artifact already staged local, pdSeparate):**
  - M2-S0 / mtbench8: prefill **141.47 s**, decode **150.67 s**
    (`request_config/mtbench8/timing.json`, `device_verdict.json`)
  - E10 A/B run: prefill **146.01 s**, decode **156.04 s**
    (`assets/2026-07-31-e10-ab-boundary/e9_timing.json`)
  - ⇒ **~140–156 s per artifact**, decode consistently a few s higher.
- **load ≠ attach — they are separate stages.** `runtime = SdkRuntime(...)`
  (attach) is UNTIMED and lives in the ~416 s bracket (interpreter start +
  artifact copytree + attach); `runtime.load()` is separately measured as
  `load_s`. So in the M2-S0 734 s run: **load ~292 s (141.5+150.7, measured)**
  + untimed bracket ~416 s + actual compute ~26 s (mtbench8 short gen). An
  earlier reasoning pass that folded the ~150 s "load" *into* "attach"
  double-counted — corrected here.
- **Caveat: `load_s` is program + weights together** (weights are baked into the
  ELF), not code-only `.text`. So ~150 s is "whole decode artifact onto the
  wafer", NOT a per-kernel code-upload figure. For a MeshJIT / on-chip PE→PE
  single-kernel fetch the relevant quantity is a few KB of `.text` over the
  fabric — a completely different order of magnitude; do not use ~150 s as its
  reference.

## Implications / next actions

- [ ] (maintain pass) fold into `topics/m2-s0-baseline-and-timer-provenance.md`
      — that note lists the untimed bracket but should also record the measured
      `load_s` values and the load-vs-attach distinction.
- Gate 3 is decode-only reload ⇒ ONE ~150 s `load_s`, not two — relevant when
  estimating a Gate-3 serve cycle.

## Pointers

- `launch_prefill.py:1654,1939-1943`; `launch_decode.py:3594,4066-4067` (the `load_s` field + timer)
- `we-m2bench/.../request_config/mtbench8/timing.json`, `device_verdict.json`
- `agent-memory/.../assets/2026-07-31-e10-ab-boundary/e9_timing.json`
- refines `memory/topics/m2-s0-baseline-and-timer-provenance.md` (untimed-bracket line ~154)
