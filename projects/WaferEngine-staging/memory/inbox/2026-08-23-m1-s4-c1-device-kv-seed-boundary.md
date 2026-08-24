# M1-S4 C1 device-KV seed boundary — 2026-08-23

**Project:** WaferEngine-staging
**Author:** codex
**Status:** captured   <!-- captured | drained -->

## What happened / finding

- For the Qwen decode path, `KVStore.truncate()` changes only host logical
  length/token-ledger state; it does not clear `XKCache_tile` or `XVCache_tile`.
  `round_reset()` reinitializes cursor banks but likewise does not clear those
  resident device-cache bytes.
- Therefore a benchmark-only C1 rejoin can preserve a longer lane's already
  seeded `[S, R_i)` bytes by suppressing its `process_kv` write until token-step
  `d_i = R_i - S`. It does not intrinsically require a separate KV reload
  transport, but it does require a prior completed, same-slot seed whose exact
  token inputs physically wrote each lane through its `R_i`.
- The implemented C1 seam rejects positive non-final rounds and does not publish
  the timed round's host ledger. It verifies only seed extent and slot identity;
  host state cannot prove the exact on-device KV bytes, so the benchmark input
  construction remains responsible for that semantic condition.
- Positive C1 also requires `KV_TRANSFER=1`; bake/no-ingress cannot install the
  rejoin metadata and must fail rather than silently run all lanes active.

## Implications / next actions

- [ ] Before any CS-3 C1 timing, construct and review a seed/timed config pair
  whose forced tokens establish the exact prefix through each lane's `R_i`.
- [ ] Charge the C1 i16 thresholds and widened metadata tile to M1-S5 SRAM;
  compile-only success is not a before/after full-model SRAM measurement.

## Pointers

- Worktree `/home/lexu/WaferEngine-staging/.worktrees/m1-ragged-execution-study`;
  pushed branch `lexu/staging/m1-ragged-execution-study`; implementation
  commit `4a4e6c3d11b8b77b835446cde507351141f95f6c`; evidence tip
  `a24beb4c6c3dcb4595dfd940fe5b8672ae9e1048`
- `models/qwen3_1p7b-decode/launch.py`, `round_plan.py`, and `src/decode.csl`
- `docs/analysis/m1-s4-c1-workload-step-review.md`
