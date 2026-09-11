# SD service source-directory selection and build preparation

When starting nc_service from a kernel repository instead of maintaining a
vendored snapshot, the existing WE_SD_PDSEP_DIR already controls kernel imports
and staging, but the prior sd_service entrypoint required a prebuilt cache.

- Added explicit `sd_service --kernel-dir`, with environment compatibility and
  unchanged vendored fallback. Directory must contain the SD host/rewind API;
  ordinary-PD csl-kernel remains a different provider. No target directory has
  yet been chosen by Le for the permanent deployment in this step.
- Added prepare modes `reload` (default), `auto` (build if missing/stale), `build`.
  Source-build delegates the selected launch_device's `_stage_code`/`_run_build`
  and StagedDispatch in-process, placing scratch and new artifact store under
  service out_dir. No copy of the compiler algorithm, no source modification,
  no existing cache overwrite. Real weights required, post-build preflight
  required; compile failure does not connect the verifier.
- Promoted the previously device-used per-run guard into `sd_run_guard.py`.
  Its child marks guarded execution; build mode requires it. Compilation and
  serving SDK allocations are tracked together under one explicit 21600-second
  cap. Guard timeout/error tests cancel only a fake submitted job ID.
- Python's generic `host` module cache makes switching sys.path insufficient:
  selecting a different tree after imports now fails and asks for a new process.
  Relative/~ paths are canonicalized before cwd changes. Actual staged source
  fingerprints are rechecked against the artifact before upload.
- Staging copies runtime/build input directories and root Python files, excluding
  root serving_cache/device_staging directories that a live checkout can contain.
  Worker and launcher still have separate filesystems; automatic staging remains.
- preparation.json records source Git HEAD/status plus content hashes and selected
  cache. Builds reject source changes during compilation. New cache path is
  out_dir/build/store/model_config; callers reuse selected_cache on the next run.
- Local validation: 309-test related suite passed; after config-envelope checks,
  10 preparation tests passed. A fresh process with WE_SD_PDSEP_DIR pointing at
  `/home/lexu/WaferEngine-staging/models/qwen3_1p7b-sd-pdSeparate` passed 20 staging
  and fake-device service tests. These are not a new source-build device pass.
- New CS-3 compile/deploy has NOT been submitted. Await the user's intended
  absolute source directory before binding and validating that deployment. GPU
  setup remains pending; no Git mutations were performed.

Pointers: `waferengine/samples/specdec/sd_kernel/{kernel_env,prepare,staging}.py`,
`sd_service.py`, `sd_run_guard.py`, and README's repository-checkout section.
