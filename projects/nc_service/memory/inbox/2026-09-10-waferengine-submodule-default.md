# WaferAGI SD submodule becomes the default source

Le explicitly selected WaferAGI/WaferEngine's main
models/qwen3_1p7b-sd-pdSeparate as a Git submodule and requested the existing
snapshot remain as fallback. This resolves the earlier source-directory question.

- Added `third_party/WaferEngine` using `git submodule add --depth 1 -b main
  https://github.com/WaferAGI/WaferEngine.git third_party/WaferEngine`.
  Parent gitlink pins `288fe8ae63b208d1ecd8c465089d7022f430c5db`. `.gitmodules`
  records branch main; startup does not fetch or follow remote updates.
- Source selection: explicit --kernel-dir, WE_SD_PDSEP_DIR, initialized
  submodule's models/qwen3_1p7b-sd-pdSeparate, then legacy kernels/ snapshot.
  An initialized but broken submodule raises instead of silently falling back.
  Source-only worker staging still uses kernels/ inside its private upload tree.
- All 54 upstream SD source files match the fallback snapshot; bytecode/pytest
  cache are excluded from that comparison. Existing compiled cache source
  fingerprint from CS-3 `~/lexu/sd_m2_store/serve_2x4_8k20k/build_manifest.json`
  matches the selected submodule with cache_fresh=true and no differences.
  Evidence: `_runs/drafting_20260910/submodule_cache_check/verdict.json`.
- Changing the default exposed legacy hard-coded kernel imports in tests.
  BridgeTarget tests now use kernel_env imports; staging/timing tests examine
  the selected provider. The separate vendor snapshot test still pins fallback.
- Default-provider related suite: 313 passed. Explicit fallback SD/device-driver
  suite: 305 passed. Three existing protobuf warnings. Submodule checkout clean.
- No new device execution or compilation in this step: compatibility evidence is
  source/cache identity plus local tests. Earlier real SD integration pass still
  applies to those identical kernel bytes; automatic source-build entrypoint
  remains untested on hardware. GPU setup remains pending.
- Only `.gitmodules` and gitlink were staged by the explicitly requested submodule
  addition. No commit/push or unrelated staging. Parent runtime/docs changes
  remain uncommitted, as do earlier session edits.

Pointers: `.gitmodules`, `sd_kernel/kernel_env.py`, root and specdec READMEs,
`kernels/VENDOR.md`, `BINARY_ADOPTION_ASSESSMENT.md`.
