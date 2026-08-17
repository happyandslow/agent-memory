# WaferLLM function-container M3 placement contract — 2026-08-15

**Project:** WaferEngine
**Author:** codex
**Status:** drained 2026-08-17 into `memory/topics/meshjit-code-relocation.md` and `plan.md`

## What happened / finding

- Phase 1 Step 3 M3 now has a source-hash-pinned, declarative ownership and
  re-entry contract for WaferLLM Decode Attention A0–A7 and FFN F0–F3b.
  It contains 24 uniquely owned components and 13 entry profiles.
- Source-shared compute helpers are not a resident common compute library.
  `vecmat_computation`, `gemv_static_step`, `fmulh_norm_func`, and `fast_exp`
  must be private-linked into each page that uses them; the receiver retains
  zero callable page-compute bodies.
- Every local hot-path span from `rmsnorm_x` through `ffn_residual_add` is in a
  fixed coverage oracle. Resident collective lines 362, 524, 542, 560, 582,
  599, 623, and 703 are excluded from page-private spans.
- Entry profiles distinguish receiver entry prebind from ordered page-local
  descriptor assignments/rebinds/length changes/increments. Yield invalidates
  every mutable DSD/DSR state; no entry relies on the preceding entry's
  descriptor contents.
- M1 pinned model/intermediate data is separate from module binder/profile
  state (`Kt`, `Nt`, `ptr_right_matrix`, mutable DSD objects, `cur_`, and
  `z2_val`). `ptr_left_vector` and `ptr_out_vector` are declared but unused in
  production and are dead-strip expectations rather than binder cost.
- Production `rmsnorm_z` rebinds `seq_len_p_pe_dsd_1` to `z_norm_tile`; the
  frozen production config happens to have `seq_len_p_pe == dim_p_pe`. This is
  a configuration-sensitive source quirk, not a general identity.
- U01–U03 remain fail-closed final-link gates: compiler math/division lowering,
  `@map`/loop/branch lowering, and global/DSD address plus DSR-kind realization.
  M3 does not claim page ELF closure or runtime correctness.
- The first Claude Code review correctly returned FAIL for missing RMSNorm body
  ownership, incomplete dual-page `fast_exp` ownership, ambiguous callback
  spans, and order-insensitive A4 transition validation. All were fixed; the
  targeted re-review returned PASS. M3 evidence SHA-256 is
  `e2e25b1531ce74b95986812bf02af32dc525542459f9601484b698b2e30faae4`.

## Implications / next actions

- [ ] Start M4 only after user acceptance. Deterministically generate the two
  production-derived page sources using the approved M2 entries and M3
  ownership/profile contracts; do not resolve U01–U03 by assumption.
- [ ] M5 must prove the unresolved call/branch/address/DSR closure in final
  address-matched ELF images before Step 3 can pass Grade E.

## Pointers

- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/STEP3_TRACKING.zh-CN.md`
- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step3-page-regions/manifests/component_placement.json`
- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step3-page-regions/manifests/entry_profiles.json`
- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step3-page-regions/manifests/unresolved_ledger.json`
- `/home/lexu/WaferLLM/MeshJit-Decode/FUNCTION_CONTAINER_DESIGN.md`
