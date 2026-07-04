# nc_service Context

Compact startup packet for fresh agent sessions. Keep this short enough that an agent can read it every time.

## What this project is

- WaferEngine **SpecDec on WSE-3**: CS-3 runs the **draft** model; an external GPU host is the
  **verifier/target**. The `io_pipeline` backbone carries advances between them. Sample lives in
  `waferengine/samples/specdec/`. v1 uses a **passthrough** kernel (ids echoed) so the whole path is
  numerically checkable before the real prefill+decode kernel drops in.

## Current state (2026-07-04 — real kernels + PD + spec-dec rewind)

- The **real prefill+decode kernel swap-in is done** (the "next action" of the June phase). Now on
  branch `lexu/specdec-real-kernels`. The real qwen3 kernels are wired into the merged **PD
  disaggregation** framework (`driver_main --pd`, pod-to-pod `kv_channel`, `appliance_handlers`
  factory seam) via `realkv/pd_real_adapters.py` (`IOP_REAL_KERNELS=1`) + the A2 `kv_transform`.
- **Validated:** `PD_REAL_SIM_PASS` (sim, KV digest matched); single real appliances **bit-exact on
  real WSE-3** at actual 28-layer size (`DECODE_RESIDENT_DEV_PASS`, `PREFILL_RESIDENT_DEV_PASS`).
- **Spec-dec decode REWIND (mode B) added and validated bit-exact in sim AND on real WSE-3** —
  v1 P-aligned, on branch `lexu/decode-rewind` **in the WaferEngine repo** (PR #13 lacked rewind).
- Two product paths, kept separate: **mode A** (regular PD serving) saved on
  `lexu/pd-disagg-modeA-serving`; **mode B** (spec-dec) is the rewind work.

## Current focus / next actions

- Full roadmap + priorities: **`memory/topics/specdec-cs3-roadmap.md`** (read this first).
- Top items: (1) **v2 token-granular rewind** (v1 is P-aligned=256 on device, too coarse); (2) the
  **mode-B host adapter** (draft/verify/accept-K/rewind-by-R loop + `n_steps=draft_len`); (3) the
  real-kernel PD **device run** (`READY_TIMEOUT=7200` + send_x N-header fix + ingress-502 hardening).

## Must-read topic notes

- **`memory/topics/specdec-cs3-roadmap.md`** — the current roadmap, done/TODO, branches, gotchas.
- `memory/topics/specdec-d2h-latency.md` — earlier d2h latency / in-process-patch / real-GPU findings.
- Root **`CLAUDE.md`** (in nc_service) — architecture + build/test/device commands.

## Important constraints

- Device runs go through the `/cs3-runner` skill (gateway TOTP via `cs3-login-cj`; never print/copy
  the secret), in the SDK `csl` conda env on CS-3, with `export PYTHONPATH=.`, under the timeout guard.
- Real GPU verifier `10.22.28.100:32245` runs a FIXED 1000-round/k=16 benchmark; disconnect before
  round 1000 fails it — serve all 1000 + `--idle-timeout`.
- Don't loop-retry cs3-ssh (EIDF rate-limit); proto stubs must stay protobuf 4.21-compatible.

## Restart checklist

1. Verify live repo/server state; memory may be stale.
2. Read `tracking/status.md`.
3. Read `memory/topics/specdec-d2h-latency.md`.
4. Proceed with the user's task.
