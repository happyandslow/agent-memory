# Drafting deployment can pass protocol checks without matching the target prefix — 2026-09-10

**Project:** nc_service
**Author:** codex
**Status:** captured

**Latest device outcome:** baseline `wsjob-3inuefcthypuly8sujupvy` is terminal.
It ran at 16:22:01 UTC and completed prefill + KV transformation, then its worker
was evicted at 16:33:41 for node ephemeral-storage pressure. Gateway INIT failed
with repeated 502s; the guard cleaned up the owned job at 16:36:35, exit=1.
No SD multi-round readiness pass. Earlier queue/run checkpoints below are
historical; details are in `2026-09-10-live-progress-pipe-and-worker-eviction.md`.

## Situation and verified findings

When resuming Cerebras drafting deployment, do not equate an M1/M2 accounting
pass with readiness for a real target. Current `main` is `dfa1f49`; the SD path
is `sd_device_check.py` + `SdSession` + `sd_kernel.handlers`, using vendored
`qwen3_1p7b-sd-pdSeparate` (`cb49130f`, in-kernel rewind). The older CLAUDE.md
`realkv` paths are stale.

- Warm CS-3 access succeeded on un02 through `CS-3-cmd`. The csl Python imports
  the SDK, grpc 1.51.1, numpy 1.25.0. Independent tracked-source snapshot:
  `~/lexu/nc_draft_validation_20260910/nc_service` on CS-3.
- Existing cache `~/lexu/sd_m2_store/serve_2x4_8k20k` passes current-source
  preflight: `cache_fresh=true`, no mismatches, max draft length 16, top_k 20.
  No new device execution occurred; this is a file/manifest check.
- Confirmed false success in `sd_device_check.run`: an actual local gRPC
  verifier rejects a 3-token batch requested as k=4, but old run() returns
  normally. Missing completion likewise returns normally. Fixed both to raise
  `SdGatewayError` **after** saving summary.json; two regressions failed before
  the fix and pass after it. SD suite: 275 passed. Changes are uncommitted and
  also synced to the isolated cluster source snapshot. No kernel edits.
- The target's initial commit never supplies the wafer prompt on this path.
  `test_the_prompt_does_not_travel_on_leg_2_in_m1` deliberately proves that
  protocol checks pass with different target/device prefixes. The target
  commit also includes its bonus token; current prefill uses its own staged
  text. `driver_main` lacks SD wiring, and the device check rejects multiple
  prompts. These remain readiness blockers, not newly implemented features.

## Next action and scope

Le explicitly requires Cerebras drafting to pass and be ready **before** work
on the gala2 GPU verifying service (`Chivier/hybrid-nn`). GPU setup and repo
migration have not begun. Le subsequently set the per-run hard cap to **6 hours
(21,600 seconds)**, including queueing and loading.

Prepared baseline: validated cache, `--draft-len 16 --rounds 60
--accept-lens 17,9,1 --max-new-tokens 1200 --num-prompts 1`, under a guard that
cancels only the identified job for this run. Inspect verifier completion,
empty failures, 61 proposal batches and matching device evidence. Passing
this fixed-prompt baseline will not close dynamic-prompt readiness.

## Same-day continuation (in progress)

- Baseline submitted under a cluster-local guard; SDK `run_meta.json` in the
  isolated checkout identifies `wsjob-3inuefcthypuly8sujupvy`. It was initially
  QUEUED and is now terminal with exit=1 (see latest outcome above). Guard output:
  `~/lexu/nc_draft_validation_20260910/baseline_k16_01/{guard.json,jobs.jsonl,driver.log}`.
  Cancellation is scoped to this recorded ID. SDK `_bare_job_id` appears only
  after scheduling, so the next guard version observes
  `ClusterManagementClient._record_new_job` to capture queued jobs immediately.
- A foreground `ssh -MN -o ControlMaster=yes -o ControlPersist=8h CS-3-cmd`
  held in the tool's live process session established reusable final-hop
  access. Attempts to park it with `-MNf` did not survive between tool calls.
  The existing OTP-authenticated gateway master was preserved throughout.
- Implemented `sd_service.py`: target-provided `emitted_ids` (including the
  bonus) staged directly to prefill; strict ledger/accepted-prefix and device
  batch-context checks; last-command replay; serial new-request isolation;
  terminal commit cleanup. It cold-loads a new worker per new request, so target
  command timeouts must cover minutes of bring-up. This is **not** resident
  multi-request/batched serving. Added worker prefix-digest evidence.
- Fixed gateway idle timeout to exclude active command processing, so it does
  not cancel a cold load. Fixed the idle test peer to stop sleeping after RPC
  cancellation (the old dummy peer held pytest shutdown until its 60s sleep
  ended; it was not a service deadlock).
- Local SD + device-driver + gateway suite: **309 passed**, process exits
  normally. Kernel sources unchanged; all changes remain uncommitted.
- New source snapshot: `~/lexu/nc_draft_validation_20260910/nc_service_live`.
  Prepared next gate: from that directory, run `../live_gate.py <new-output-dir>`
  via `../run_guard.py --seconds 21600 --out <new-guard-dir> -- ...` only after
  baseline passes. It checks 13 real device batches with k=16 and target
  accept lengths 17/9/1, plus exact gateway/worker committed-prefix digest
  equality. `SD_LIVE_PREFIX_DEVICE_PASS` is the pass token. Not yet launched.
- A foreground cluster-side continuation was prepared to wait for baseline guard
  completion, then stopped on migration steering. It checked exit=0, verifier completion/no failures, 61 k=16
  batches and 61 device TSC rows before automatically starting the live-prefix
  gate under its own 21,600s guard. Its outputs will be
  `~/lexu/nc_draft_validation_20260910/live_prefix_01/`. Do not manually submit
  a duplicate live-prefix run: inspect that directory and the waiting process
  first. Baseline failure prevents the second submission.
- The next-run guard was exercised with a local fake SDK and fake `csctl`:
  a queued child exceeded a 2s cap, returned 124 and cancelled only the recorded
  synthetic job ID. Closing the observer's stdout pipe produced the same
  result. Guard progress output now tolerates `BrokenPipeError`; this version
  is synced for the subsequent live-prefix run. The already-running baseline
  keeps its original loaded guard, with its queued job ID recorded explicitly.
- The synced `sd_service.py --help` imports and exits successfully in the
  actual CS-3 `csl` Python environment. This validates environment compatibility
  only; the device job remains queued.

## Migration direction corrected by Le (discussion pending)

- Le identifies `kernels/qwen3_1p7b-sd-pdSeparate` as legacy and requires the
  integration to move to `waferengine/csl-kernel`; read its README and discuss
  migration first. No migration edits have been made yet. The old-path baseline
  is now reference evidence only, not sufficient for the requested readiness.
- Authenticated GitHub API checked `lausannel/nc_service` main
  `dfa1f492ffdc980f28c16e4f613af299fc0bd65d`: all 22 `waferengine/csl-kernel`
  files match the local checkout. Its README explicitly says MOCK delivery;
  the only files in the ELF directories are README.txt placeholders. Real
  prefill/decode `.run()` methods raise NotImplementedError. The public API is
  complete-answer `serve(prompts)`, derived from e2e-pdSeparate, with no SD
  accepted-count/rewind interface. Two mock requests passed; real manifest
  validation rejects the placeholder bundle before execution.
- Proposed (not yet agreed): package the existing compiled SD cache as the new
  bundle, implement artifact-backed SD begin/advance/close under `pd_serving`,
  reuse the existing rewind-capable runtime, then switch service imports and
  rerun real-device gates before removing legacy paths. Asked whether Le has a
  separate real precompiled bundle location; no answer at this checkpoint.
- Stopped ONLY the waiting legacy follow-up chain (PID 291145) after verifying
  it had no child and `live_prefix_01` did not exist. It must NOT auto-launch
  after baseline now. Baseline later ran and failed before the original 21,600s
  cap (deadline 2026-09-10 17:48:54 UTC); see the latest outcome above. The earlier
  long delay was queueing, not recompilation.

## Pointers

- `/home/lexu/nc_service/waferengine/samples/specdec/sd_device_check.py`
- `/home/lexu/nc_service/waferengine/samples/specdec/tests/test_sd_device_check.py`
- `/home/lexu/nc_service/waferengine/samples/specdec/sd_kernel/tests/test_m1_gate.py`
- [ContextBase deployment audit](https://context.ed-aisys.com/doc/2026-09-10-cerebras-drafting-deployment-audit-and-readiness-gaps-ETwiLt1e0j)
