# Interpreting migrated drafter latency and process placement — 2026-09-12

**Project:** nc_service
**Author:** codex
**Status:** captured; source inspection, no new device measurement

When reading NC_Service timing reports or deciding whether a request is warm, avoid equating artifact reuse with resident execution or gateway RTT with verifier latency.

- `/home/lexu/NC_Service/docs/architecture.md` now documents packages, actual gateway/worker/process/thread placement, numbered protocols, lifecycle, proto compatibility, timing and progress. Editable figures: `docs/diagrams/{package-map,execution-path}.excalidraw`; sibling SVGs are derived previews. Diagram labels and 22 local document links checked; no runtime changes or new CS-3 execution.
- `rpc/client.py` measures on the gateway. `pump_exchange_ms` includes parse_request + full RequestSessions advance, hence cold worker bring-up/prefill/decode load on first request. service-level prepare/build happens before the stream and is excluded. Warm rounds reuse one resident decode runtime; a different request creates a new backend.
- Two driver RTT definitions coexist: returned `rtts`/SPECDEC_TIMING uses a continuous span ending before envelope creation and enqueue; `session.json` python_rows driver_rtt_ms sums exchange + response construction/copy + envelope + enqueue. Neither waits for verifier receipt. python_stage1_ms excludes advance, so is not total host-Python overhead. These are code facts, not performance measurements.
- External DraftControl server belongs to verifier; gateway is its outbound client. Worker hosts the separate patched SDK server. `inproc_patch/controller.py` executes in the worker pod, not on the gateway. Prefill is a child process; decode is a thread inside patched SDK server. KV passes through worker-local NPZ between two programs loaded sequentially on one wafer.
- Schema preservation is a compatibility choice, not a claim every field is implemented: client ignores command timeout_ms, and the unary DraftRuntimeService declared in draft.proto is not served by nc-draft. Simplifying runtime implementation need not delete wire definitions.

No Git staging/commit/push. Preserve user edits when continuing review.
