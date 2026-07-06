# nc_service Context

Compact startup packet for fresh agent sessions. Keep this short enough that an agent can read it every time.

## What this project is

- WaferEngine **SpecDec on WSE-3**: CS-3 runs the **draft** model; an external GPU host is the **verifier/target**. The `io_pipeline` backbone carries advances between them.
- The current real-kernel path uses the merged **PD disaggregation** framework (`driver_main --pd`, pod-to-pod `kv_channel`, `appliance_handlers` factory seam) plus real qwen3 prefill/decode adapters.
- Two product paths are intentionally separate: **mode A** = regular PD serving; **mode B** = speculative decoding with decode-position rewind.

## Current state (2026-07-06 — from memory notes, not live repo recheck)

- The real prefill+decode kernel swap-in is done on the memory-recorded branches (`lexu/specdec-real-kernels`, `lexu/decode-rewind`, `lexu/pd-disagg-modeA-serving`).
- Validated: `PD_REAL_SIM_PASS`; single real appliances bit-exact on real WSE-3; decode rewind v1 and **token-granular v2** validated bit-exact in sim and on real WSE-3.
- Mode-B adapter progress is substantial: sim pass, device window pass, partial-accept accounting fix, full adapter-chain `MODEB_DEV_PASS`, framework factory dispatch, and exchange-batch sim pass are in the roadmap topic.
- A full-loop runner (`run_e2e_pd_modeb_sim.sh`) is built but not yet successfully run; it needs the CS-3 `csl` conda env and has been blocked by intermittent gateway/auth issues.

## Current focus / next actions

- Full roadmap + priorities: **`memory/topics/specdec-cs3-roadmap.md`** (read this first).
- Top items: (1) run the full mode-B PD/spec-dec sim loop on CS-3 (`mock_verify_host` `failures:0`); (2) run partial-accept on device and connect the real GPU verifier; (3) complete mode-A transport hardening (`READY_TIMEOUT=7200`, send_x N-header fix, ingress-502 retry) for `PD_REAL_DAEMON_DEV`.

## Must-read topic notes

- **`memory/topics/specdec-cs3-roadmap.md`** — current roadmap, done/TODO, branches, gotchas.
- `memory/topics/specdec-d2h-latency.md` — earlier d2h latency / in-process-patch / real-GPU findings.
- Root **`CLAUDE.md`** (in nc_service) — architecture + build/test/device commands.

## Important constraints

- Device runs go through the `/cs3-runner` skill (gateway TOTP via `cs3-login-cj`; never print/copy the secret), in the SDK `csl` conda env on CS-3, with `export PYTHONPATH=.`, under the timeout guard.
- `cs_python` is not enough for the full-loop driver because it lacks `cerebras.sdk.client`/`SdkLauncher`.
- Real GPU verifier `10.22.28.100:32245` runs a fixed 1000-round/k=16 benchmark; disconnect before round 1000 fails it — serve all 1000 + `--idle-timeout`.
- Don't loop-retry cs3-ssh (EIDF rate-limit); proto stubs must stay protobuf 4.21-compatible.

## Restart checklist

1. Verify live repo/server state; memory may be stale.
2. Read `tracking/status.md`.
3. Read `memory/topics/specdec-cs3-roadmap.md`.
4. Read `memory/topics/specdec-d2h-latency.md` only if working on backbone/latency history.
5. Proceed with the user's task.
