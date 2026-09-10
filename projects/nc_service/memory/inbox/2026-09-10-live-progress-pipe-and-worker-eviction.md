# Reading progress while CS-3 SD initialization is busy — 2026-09-10

**Project:** nc_service
**Author:** codex
**Status:** captured

## Situation and verified findings

When a CS-3 SD job is RUNNING but gateway stdout is silent, the h2d-playground
file/FIFO polling technique is relevant, but cannot be copied directly into the
current in-process worker protocol.

- Memory pointer: WaferEngine `docs/2026-07-14-h2d-playground-experiments.md`,
  section e9-launcher-polling. Source verified with `git show lexu/h2d-explore`
  in `/home/lexu/WaferEngine`: `h2d-playground/e9-launcher-polling/{daemon,stress,relay}.py`.
  The daemon writes unbuffered timestamp/sequence lines to `/tmp/stream.bin`
  (regular file) or `/tmp/stream.fifo` (named pipe). Controller issues bounded
  `launcher.run("dd ...")` reads with byte offsets; relay exposes SSE. This is
  polling, not streaming stdout from one long-running launcher call.
- Current `executor/inproc_patch/handler.py` replaces shell execution with
  protocol dispatch. Its `_LOCK` encloses INIT, PING, TIMING and exchanges, so
  `__IOP_TIMING__` cannot observe a concurrently blocked INIT. It has no general
  file-tail or progress verb. Local and deployed baseline source SHA256 match:
  handler `d7fa0e8b1f010340ef108c8fe15c62e288b993acdbf9a1b6ec97f717f5f6e137`.
- `source_transform.py` wraps every `sdk_download_files` completion with a
  restore sentinel; the controller then terminates the patched worker and
  restores the original server. Do not use `download_artifact` for live polling.
  Matching deployed SHA256:
  `0499b453de75102fd523d6a4b25c86f94c357bceee7be5574bd4cadbd26dbaf2`.
- Existing worker log is `inproc_patch_worker.log`. Prefill runs with Python
  `-u` and inherits this file; `sd_run/sd_setup.json` appears after prefill and
  KV transformation. These are phase evidence, not a complete live status API.
- `csctl log-export` independently retrieved worker logs during this job and
  after termination, without invoking the patched download RPC. Existing output
  directory is required. On this cluster `--num-lines 100` failed with
  `numLines cannot be used with skipClusterLogs`; omitting that flag succeeded.

## Current baseline outcome (supersedes earlier queued/running checkpoints)

- Job `wsjob-3inuefcthypuly8sujupvy`: scheduled 16:21:47 UTC, RUNNING at 16:22:01
  on xs20741. Prefill produced a first token and KV for the staged 19-token prompt;
  its verdict and `sd_setup.json` confirm prefill + KV transformation completed.
- At 16:33:41 UTC, csctl records worker exit 137 and node
  `net001-wk-sr03` eviction due to low **ephemeral-storage**. This is the reported
  node resource cause; the share attributable to our artifacts was not measured.
- Gateway INIT subsequently failed after 60 seconds of repeated ingress 502s.
  The run guard cancelled the recorded owned job at 16:36:35 UTC; guard exit=1,
  elapsed=17261 seconds, below its 21600-second cap. No SD multi-round pass or
  decode verdict was recovered. No automatic retry or GPU run was launched.
- Evidence on CS-3 under `~/lexu/nc_draft_validation_20260910/`:
  `baseline_k16_01/{guard.json,driver.log,jobs.jsonl}` and
  `log-export-wsjob-3inuefcthypuly8sujupvy-6fd27a7c.zip` (worker-only export).

## Implementation and revalidation after Le requested the feature

- Implemented host-only progress journaling in `engine/io_pipeline/progress.py`:
  per-event start/done/error records, stable path under IOP_SRC, independent byte
  offsets, bounded complete-line reads, and working-filesystem free bytes.
- `__IOP_PROGRESS__ <offset>` is handled before the execution lock. Gateway
  `progress_monitor.py` polls the existing SDK stub with a five-second deadline
  and emits `IOP_STAGE` / `IOP_PROGRESS` to driver.log. It never downloads an
  artifact; the monitor stops before restoration. The original INIT remains
  in flight throughout prefill/decode bring-up.
- Phase adapters wrap runtime copy/attach/load/run/send/receive/stop without
  modifying upstream kernel files or ELF. A prefill child wrapper instruments
  that subprocess too. Feedback waits and draft batch boundaries are recorded.
- Local validation: 329 tests passed in the combined SD/bridge/progress suite,
  plus one phase-wrapper forwarding/restoration test. A real local gRPC test
  reads progress during blocked INIT and blocked exchange, with replay intact.
- Explicitly authorized device revalidation uses `sd_service` and the prepared
  raw-prefix live gate (13 k=16 batches, acceptance 16/8/0, prefix digest and TSC
  checks), with a fresh isolated source snapshot `nc_service_progress_01`.
  Cache preflight still reports fresh; no compilation. Job
  `wsjob-jmrgvdhasyfnjpi4hku9fa` on xs20774, evidence directory
  `~/lexu/nc_draft_validation_20260910/progress_live_01/`; new 21600-second guard.
- Device observation verified at 19:15 UTC: while INIT remained in flight,
  gateway received worker `config.read done`, `prompt.ready` (8 raw IDs), and
  the prefill child PID 296's `prefill.copy_cache_to_run start`. Thus the actual
  SDK/coordinator permits the independent read while initialization is busy.
  Observation passed independently of SD readiness. That first instrumented
  run later failed: 37 events and 104 successful progress responses were saved;
  prefill and KV completed, last active stage was decode.copy_cache_to_run, and
  minimum reported workdir availability was 49,088,942,080 bytes. csctl records
  another ephemeral-storage eviction on net001-wk-sr03 at 19:24:32 UTC. Guard
  exit=1; full local evidence is `_runs/drafting_20260910/progress_live_01/`.
- Added a stage around SdkRuntime construction after observing a long interval
  between attach and load; this does not relabel that interval as load time.
- Fixed avoidable peak storage in the host adapter: only after the prefill child
  exits AND all KV outputs are transformed/saved, remove the completed phase's
  scratch `sim.elf`. Preserve the delivered cache, KV and verdict; skip source
  aliases/symlinks. The first instrumented run kept both large scratch images
  concurrently when eviction occurred. This mitigation's effectiveness still
  requires device evidence; do not infer node-wide space from workdir statvfs.
- Storage/observer/phase tests: 43 passed after the final change, including
  source/KV/verdict preservation. New isolated snapshot `nc_service_progress_02`
  and evidence `progress_live_02/` were launched under a fresh 21600-second guard
  only after the first guard exited. Full SD gate pending at this checkpoint.

## Design constraints / remaining validation

- Keep progress independent of the execution lock/replay state and use the
  existing SDK run-command method rather than a coordinator-filtered new RPC.
- Prefer file offsets for observation; a second FIFO consumer can steal records
  and missing readers can block a writer. Keep restore separate from observation.
- Host-side instrumentation need not change CSL/ELF. Test INIT-held-lock queries,
  bounded incremental reads, and no restore/replay side effects before device use.

## Pointers

- `waferengine/engine/io_pipeline/executor/inproc_patch/{handler,source_transform,controller}.py`
- `waferengine/engine/io_pipeline/gateway/bridges.py`
- `waferengine/samples/specdec/sd_kernel/{handlers,serve_setup}.py`
## 2026-09-10 19:44 UTC — Real draft integration gate passed

- Second instrumented job `wsjob-razycbqrm8gbvtkmjmafnb` completed on xs20774: csctl SUCCEEDED at 19:44:21 UTC, no error replicas; guard exit 0 after 1014.288 s, within 21600 s.
- `SD_LIVE_PREFIX_DEVICE_PASS`: real Cerebras draft plus CPU mock verifier, 12 feedback rounds (16/8/0 accepted), 13 batches of 16 tokens, 13 device_tsc rows, exact target/gateway/worker input digest match for the 8 committed IDs. This is an integration smoke gate, not GPU verification or a new numerical-oracle comparison.
- Prefill scratch image release actually removed 22,893,155,848 bytes after KV save. This run had no storage eviction; it does not guarantee immunity to node-wide pressure.
- Observation limitation: 87 successful progress reads and 29 timeout reports; decode runtime construction (135.43 s) and load (153.44 s) executed during the RPC gap. Events were later replayed. GIL retention is an unconfirmed hypothesis; a last-received stage is stale evidence during observation failure, not proof of a stalled call.
- Independent csctl log-export succeeded but omitted sd_progress.jsonl while including inproc_patch_worker.log. A final local-only refinement mirrors/flushed stage rows to stdout before each call, providing that independently exported log with future stage boundaries. No claim of five-second log-export freshness.
- Other local-only refinements after the device snapshot: preserve atomic locking for whole streamed legacy command batches; drain final progress backlog (16 pages / 10-second budget); worker.restore stage messages. Run02's final single-page drain retained only 411 of the journal events in driver.log. Full 13-batch evidence is independently in backend.json/verdict.json.
- Validation: final combined suite before stdout refinement 333 passed (3 existing protobuf warnings); subsequent progress/observer suite after stdout refinement 8 passed. These final local changes have not been redeployed in another device run.
- Evidence on gala2: `/home/lexu/nc_service/_runs/drafting_20260910/progress_live_02/`, including result/verdict.json, result/service/request_0001/backend.json, guard.json, driver.log, and independent log-export ZIP. Remote source snapshot is `~/lexu/nc_draft_validation_20260910/nc_service_progress_02`.
- No active validation job remains. Kernel source/artifacts unchanged; no compilation, Git commit, GPU setup, or migration performed. Migration discussion still precedes GPU setup per Le's requested order.
