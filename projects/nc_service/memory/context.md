# nc_service Context

Compact startup packet for fresh agent sessions. Keep this short enough that an agent can read it every time.

## What this project is

- WaferEngine **SpecDec on WSE-3**: CS-3 runs the **draft** model; an external GPU host is the
  **verifier/target**. The `io_pipeline` backbone carries advances between them. Sample lives in
  `waferengine/samples/specdec/`. v1 uses a **passthrough** kernel (ids echoed) so the whole path is
  numerically checkable before the real prefill+decode kernel drops in.

## Current state

- Active branch `lexu/toy-emit-recv-modes` (off main, NOT merged; PR being prepared, not opened).
- Backbone settled: **in-process gRPC patch** (`--bridge inproc`) + **batch d2h receive**
  (`--recv-mode batch`). Real GPU verifier validated: verify-side p50 **3.30 ms** (batch), 0 errors.
- Deep context + all numeric tables in ContextBase log `GOZQ9I8pOe`; topic note
  `memory/topics/specdec-d2h-latency.md`.

## Current focus

- Branch cleanup + prepare a PR for `lexu/toy-emit-recv-modes` (do not open until Le says so).

## Next likely actions

- [ ] Finalize PR prep (rebase/squash decision, PR description) — do not open without Le.
- [ ] Ask GPU service owner for RAW per-round latency dump (exact verify-side distribution).
- [ ] Per-step full-1000 benchmark vs the real service (GPU-measured both-modes comparison).
- [ ] Real prefill+decode kernel swap-in.

## Must-read topic notes

- `memory/topics/specdec-d2h-latency.md` — the d2h latency / in-process patch / real-GPU verify-side
  findings, numbers, commands, and pitfalls. Read before any latency or benchmarking work.

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
