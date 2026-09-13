# Large kernels must be run on CS-3, not simfab: the simfab trace is too big and hangs the run; check disk before launching — 2026-09-13

**Project:** wse3-performance-model (applies to WaferEngine-staging work too)
**Author:** claude (session 4b-layout-kv-stream), instruction from Le
**Status:** captured
**Kind:** feedback / procedural

## Situation

You are about to validate or time a full-size kernel (e.g. the Qwen3-4B
decode 4-row × 256² layout, or the KV-farm variant) and you reach for
`run_sim.sh` / simfab because it needs no device slot.

## What Le said (2026-09-13, verbatim intent)

"大号的 kernel 一定要放到 CS-3 上去跑（trace 太大会卡住，检查一下 disk）" —
the big kernel MUST run on CS-3. Simfab on the full-size geometry produces a
trace that is too large, the run hangs, and the disk fills. Check the disk
before launching anything sim-sized.

Second statement, later the same day: **anything larger than 16 × 16 PEs goes
to CS-3** — on the local machine it would "run until the next life (or blow up
first)". So the local simfab ceiling is a 16 × 16 kernel; the `sim_2x2` family
(P = 8) is fine, anything device-shaped is not.

## Observed the same day

- `run_sim.sh` already exports `SINGULARITYENV_CSL_SUPPRESS_SIMFAB_TRACE=1`
  unless `SIMFAB_TRACE=1`; with it suppressed, a `sim_2x2` artifact is ~2 MB.
  Do not set `SIMFAB_TRACE=1` on anything but the smallest geometry.
- Even the small `sim_2x2_longkv`-class geometry (P = 8, 2 × 2 blocks) with a
  512-token prefill needed ~45 s for the first decode step and was still on
  step 1 after 25 minutes at bsz = 1 — use short requests (prefill 64,
  decode 4: `request_config/sim_farm_short.json`) for functional bisects.
- gala2 disk at the time: `/home` 3.5 T with 474 G free (86 %), `/` 440 G
  free; `/home/lexu/build` = 26 G, of which each device artifact dir
  (`out_device_2x4_8k*`) is 8.6 G.
- Device runs still need Le's explicit go for every CS-3 job.

## How to apply

- Simfab: only the `sim_*` configs, short requests, trace suppressed; check
  `df -h /home` first and delete stale `out_*` artifact dirs.
- Anything at the shipped 761 × 1026 placement (device configs): compile
  locally (`--compile-only`), then run on CS-3 via `launch_device.py` /
  `run_device.sh` after Le says go.

## Pointers

- `/home/lexu/build/4b-farm/s1/qwen3_4b-decode/run_sim.sh`, `run_device.sh`
- related: `2026-09-13-kv-farm-late-merge-small-scope-sync.md`
