# Cerebras-only repository migration scope — 2026-09-12

**Project:** nc_service
**Author:** codex
**Status:** captured

## What happened / finding

- When deciding whether to continue hybrid-nn/tokenizer integration, Le explicitly changed the current goal: preserve the existing RPC interface, clean up the Cerebras drafting service, and migrate to a new repo. Requested a subagent's overall design-cleanliness assessment first. This supersedes GPU integration as the immediate work item; it does not authorize deleting code or Git operations.
- Read-only parent + subagent survey confirms the live Python SD service does not use the Rust mock runtimes, ordinary-PD csl-kernel package, or old model_adapter. Its real KV transform comes from the selected external kernel's host.kv_bridge. The current checkout has no realkv directory despite older instructions mentioning it.
- Main cleanup dependency: sd_service imports bootstrap/staging/timing helpers from sd_device_check and inproc_bridge_check. Extract those before omitting old drivers. Whole-specdec staging currently carries unused product paths.
- Current root/sample protobuf copies are byte-identical. Preserve wire schema AND outbound stream/session/version/round/replay/finalization semantics. SDK worker patch, kernel target injection, progress and owned-job guard are active dependencies, not disposable mock code.
- Inventory: git-tracked .py/.rs/.csl/.proto/.sh physical lines including tests/comments, excluding third_party and generated _pb2 names: 72,020 total; 34,428 excluding kernel snapshots. Rust + benchmarks + csl-kernel + model_adapter total 12,609 lines / 91 files (~37% of non-kernel source) can be omitted under the new product scope after dependency extraction. Not a dead-code metric. Untracked converter work and C/H/docs/artifacts are outside this denominator.
- Prior user-requested legacy kernel fallback remains a compatibility requirement pending an explicit policy decision. Do not treat scope reduction as cancellation of fallback. Keep existing converter work outside the new core rather than discarding it.

## Implications / next actions

- Suggested, not yet implemented: one Python package with RPC, session, Cerebras backend, worker transport, artifact management and observability boundaries; external pinned WaferEngine provider; focused tests/tools.
- Migration is not complete until a new entrypoint passes the existing real-device prefix/accounting gate with matching artifact/source identity and runtime guard. This assessment ran no tests or device jobs and changed no runtime code.

## Pointers

- /home/lexu/nc_service/docs/CEREBRAS_DRAFT_MIGRATION_ASSESSMENT.md
- /home/lexu/nc_service/waferengine/samples/specdec/sd_service.py
- /home/lexu/nc_service/waferengine/samples/specdec/inproc_bridge_check.py

## Minimal migration pack prepared

- Le requested the minimal migration list before supplying a destination. Prepared `/home/lexu/nc_service/docs/minimal-migration-pack/{README.md,manifest.json}`; destination is explicitly null. This is a transformation manifest, not an executable archive or dependency-closed package.
- Manifest records 82 unique source files with working-tree SHA-256, actions and provisional targets, including 41 test/fixture files and four generated-stub compatibility baselines. All paths and hashes validated. Preserve exact root proto; regenerate packaged Python stubs with the deployed protobuf/grpc compatibility constraints.
- Explicitly promote ignored `_runs/drafting_20260910/live_gate.py` into a parameterized operational gate. Retain SDK-free `sglang_shapes.py` only as test message construction support; it does not mean migrating the SGLang verifier.
- No runtime extraction, destination creation, install/device test or Git mutation occurred. Recheck source hashes and destination instructions/status before consuming the pack.

## Destination supplied and architecture proposed

- Le supplied `https://github.com/MeshInfra/NC_Service` and requested an architecture proposal after repairing a premature stash-pop conflict. Read-only destination inspection found main `161d96d157fa7ea6a4a8905834467d152e2b01ae` with only README and .gitignore. No destination runtime or local path has been created by this work.
- Le explicitly authorized the per-file Git restore and main update. Local nc_service main fast-forwarded from dfa1f49 to `35288049532bca766d337d3f8df87c3cfce2041b`; reapplied only the original five-line token-bridge README addition. No unmerged index entries remain; stash and other local work preserved. All 82 migration source hashes still match.
- Proposed, not approved/implemented: one `cerebras_draft` Python package with RPC client, authoritative session ledger, Cerebras backend, worker transport, deployment/artifact lifecycle and observability. Gateway and executor are two execution locations within this product. Keep existing kernel/SDK compatibility patches isolated and preserve callback/replay/finalization semantics; no new tokenizer or GPU integration in this migration.
- Proposal: `/home/lexu/nc_service/docs/minimal-migration-pack/ARCHITECTURE.md`. Manifest now records destination URL, inspected target head and validated source-main head; local destination path remains unset.
