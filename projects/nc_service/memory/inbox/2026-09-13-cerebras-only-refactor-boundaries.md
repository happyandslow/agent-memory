# Reviewing the Cerebras-only migration after internal paths changed — 2026-09-13

**Project:** nc_service
**Author:** Codex
**Status:** captured

## What happened / finding

- When working in `/home/lexu/NC_Service`, old migration paths are now historical: gateway modules live at package top level; protobuf conversion and outbound OpenStream live in `rpc/stream.py`; the entire executor payload is `worker/`. Upload that directory plus root `__init__.py`; there is no handwritten worker manifest. Worker imports never depend on gateway/RPC. External WaferEngine stays pinned at `288fe8ae63b208d1ecd8c465089d7022f430c5db` and unchanged.
- Refactor was discussed and implemented with existing Claude Code session `nc-service-migration`, model `claude-fable-5-1`. Final independent local validation: 446 pytest cases passed; 180 response + 80 wire golden cases matched the saved baseline; fresh wheel/staged-worker import closure passed; no import cycles. These are local results, not a new CS-3 build/run or performance claim. No Git mutation or hardware run occurred.
- Do not broaden recoverable RPC errors indiscriminately. A failed multi-poll `DeviceExchange` returns no last sequence; continuing the same worker can produce replay keys `[1,2,2,3]`. Final code catches only typed pre-device `LedgerError` as a new correlated 503; device `SdGatewayError` stays terminal. Existing transport `ExchangeError` already returned 503 in the baseline. Unsupported K remains 400 (K=0 now also 400); invalid-token `ValueError` stays terminal. Even a rejected ledger command consumes outer RPC seq, but no worker exchange occurs.
- Offline `prepare.py` owns source checks; it must not import request-device orchestration. Worker environment suppresses gateway-only `WE_SD_PDSEP_DIR` in both shell command and captured SDK environment; the staged provider must win. First-batch timeout is explicitly forwarded, not ambient all-IOP copying.
- `IOP_PROGRESS` is still a path. `IOP_PROGRESS_LEVEL=stage|io` controls detail. Stage mode must retain prefill load/run/stop even without a TSC collector. Instrumentation installation itself must be inside restoration scope, not just its body.
- Current gateway command timing is one continuous `rtt_ms` through response enqueue, with separate `wait_ms`. Summary v4 joins each backend separately, uses recorded PENDING sequences, and treats unmatched worker rows as unattributed (failed exchanges can lack successful pump rows). Peer residual requires unique command IDs or an explicit order declaration; equal lengths or duplicate IDs are insufficient. Residuals include host work, and same-host provenance is not a remote GPU lower-bound measurement.
- Full-suite-only hangs were caused by tests leaving upstream `RandomTargetMock` rebound to stale queues; test cleanup now restores the actual entry binding. Upstream launch code also inserts its own `sys.path`, so idempotence tests compare the change, not an absolute count across unrelated prior imports.

## Implications / next actions

- Review the uncommitted tree via `docs/refactor-changes.md` (164 physical file changes: 60 added, 21 modified, 83 deleted; moves count on both sides), `docs/refactor-decisions.md`, and refreshed architecture diagrams.
- Device acceptance remains the guarded `tools/live_prefix_gate.py` path after local review. Source compilation and hardware runtime compatibility remain separately unverified for the refactored package.

## Pointers

- `/home/lexu/NC_Service/docs/refactor-changes.md`
- `/home/lexu/NC_Service/docs/architecture.md`
- `/home/lexu/NC_Service/_runs/refactor-review/final-validation.json`
- `/home/lexu/NC_Service/_runs/refactor-review/claude-final-review.json`
