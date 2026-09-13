# Cerebras drafter extracted into the review repository — 2026-09-12

**Project:** nc_service
**Author:** codex
**Status:** captured

## What happened / finding

- When moving the Cerebras-only drafter into MeshInfra/NC_Service, Le explicitly requested local migration to `/home/lexu/NC_Service` following the proposed layout, with no code submission. Local extraction is implemented; destination HEAD remains initial `161d96d157fa7ea6a4a8905834467d152e2b01ae`, with no staging, commit or push. The old nc_service tree and its 82 manifest source hashes remain intact.
- New installable `cerebras_draft` package separates RPC, immutable internal commands/session ledger, request device lifetime, kernel integration, worker transport, deployment and observability. Production no longer imports old `waferengine`, check scripts, tools or tests. Bootstrap/preflight/timing functions were extracted rather than carrying experiment drivers into production.
- Worker package upload is a 22-file explicit manifest. The independent pinned WaferEngine checkout lives at `third_party/WaferEngine` in the new directory; HEAD288fe8ae63b208d1ecd8c465089d7022f430c5db, upstream remote configured, no shared Git object alternates. It is an ignored standalone checkout, NOT a staged submodule. `tools/fetch_kernel.py` reproduces it. External-directory and legacy fallback lookup remain supported; legacy snapshots were not copied into the core.
- Existing compatible Python protobuf stubs were repackaged with qualified imports; descriptors and canonical proto stay unchanged. Regeneration helper requires gateway-compatible grpcio-tools1.51.1/protobuf4; no generator run in the real SDK environment occurred.
- Local validation: 415 passed, three existing protobuf warnings; Python3.13, grpcio1.81.0, protobuf4.21.12, numpy2.4.4. Tests include real local gRPC, fake device using upstream host code, request/replay/finalization, guard script/module invocation, explicit prefill-child provider import, and staged imports. Seven tests solely for retired legacy modes were removed explicitly; no silent skip of failures.
- Final wheel passed all-production-module imports and worker staging from `/tmp` under isolated Python, with no old namespace import. Production Python:42 files/4975 physical lines excluding generated stubs. Test/support and tools are separate. Final authored artifact inventory has123 files, including empty package initializers.
- No new CS-3 execution, source compilation, GPU verifier or tokenizer integration was performed. This is a locally validated migration for review, not fresh device readiness. Guarded live-prefix gate was promoted to `tools/live_prefix_gate.py` and parameterized.

## Implications / next actions

- User reviews `/home/lexu/NC_Service`; do not commit/push merely because local tests passed.
- Before claiming real-device migration success, run the existing live-prefix gate under the runtime guard in the actual SDK environment using source-matched artifacts. Source-build validation remains separate.
- Installed production entrypoint is `nc-draft`; guard supports `nc-draft-guard ... -- -m cerebras_draft ...`. Operational tools require the checkout (tests/support is intentionally outside the wheel). Launch example is executable shell rather than an unused TOML config layer.

## Pointers

- /home/lexu/NC_Service/README.md
- /home/lexu/NC_Service/docs/architecture.md
- /home/lexu/NC_Service/docs/migration.md
- /home/lexu/NC_Service/docs/migration-inventory.md
- /home/lexu/NC_Service/docs/validation.json
- /home/lexu/NC_Service/_runs/migration-validation/pytest.log
