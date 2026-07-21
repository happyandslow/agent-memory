# Adding TSC timing to the e2e model on device: the `<time>` library breaks, and a new .csl silently fails to compile

Date: 2026-07-21 · Repo: `WaferEngine-staging` · Branch: `lexu/staging/kv-transfer-bandwidth`

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured

## Situation

Instrumenting the prefill→decode KV handoff in `qwen3_1p7b-e2e` with a per-PE TSC
segment profiler, then moving it from sim to a device (CS-3) run. Two non-obvious
toolchain traps cost real time; both are specific to how this model is built.
(The bandwidth methodology itself is in topic `prefill-decode-transfer-bandwidth.md`;
this note is the toolchain gotchas that are not in it.)

## Gotcha 1 — the `<time>` library's `get_timestamp` won't compile in this model

This model ships `scripts/cslc_bin`, a wrapper that **caps inlined loop iterations at
8**. The `<time>` library's `get_timestamp` uses an inline-for that exceeds that cap,
so it fails to compile — even though the standard SDK examples use `<time>` fine.
**Workaround: read the TSC registers directly** via `@get_config` /
`tile_config.addresses.TIMESTAMP_COUNTER` (exactly what the library does, minus the
inline loop). Verified valid: the direct read gave numbers in-family with the run's
other TSC measurements and 256/256 PEs reported. Do NOT edit the shared `cslc_bin`
wrapper. **Promotion candidate** for the `cerebras-sdk-pe-timestamp-timing` skill.

## Gotcha 2 — a new .csl not in `FILES_TO_STAGE` fails device compile silently-ish

Device egress needed a new `kv_prof_mux.csl` (streams the reporter PEs' TSC burst
off-chip, mirroring the `is_tsc_pe` logits-mux path; `read_symbol` is sim-only). But
`launch_device.py` has a **fixed `FILES_TO_STAGE` list** — a new `.csl` not added to
it makes the device compile fail with "Could not find source code." Add every new
kernel source to that list before launching, or you burn a device slot on a compile
that never had the file.

## Also confirmed this session (already placed elsewhere, noted for cross-ref)

- **WSE-3 clock is 1.1 GHz in this repo** (`bench/.../utils.py` `FREQ_GHZ=1.1`,
  `pdSeparate/launch.py:3125`), NOT the SDK bandwidth-test's 850 MHz — a 29% error if
  you use 850. The `cerebras-sdk-pe-timestamp-timing` skill was corrected (v1.1.0).
- **e2e sim dumps full device state** (`SimfabConfig(dump_core=True)`,
  `launch.py:2809`) → tens–hundreds of GB per run; 7 parallel profiling sims filled
  the disk. Recorded in `project.md` pitfalls: sim is for small `test_sim_*` configs
  only; profiling / large-PE / bandwidth runs go on device, not sim.
- Segment profiler result (sim, toy 16 KiB dim=64) was **transfer-bound, not
  compute-bound** (prep ~2.4%), overturning the prep-bound hypothesis — but it is
  overhead-dominated toy scale, and A+B+C is a decomposition, not wall-clock latency
  (B prefill-shift and C decode-ingress are the same movement seen from both ends and
  overlap). Real GB/s needs the device config (dim=2048, ~28 MB) or a PREFILL_LEN
  sweep (slope = bandwidth; a single small point measures fixed overhead α, not BW).
