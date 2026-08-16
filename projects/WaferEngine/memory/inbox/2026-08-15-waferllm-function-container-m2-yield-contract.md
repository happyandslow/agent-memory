# WaferLLM function-container M2 yield contract — 2026-08-15

**Project:** WaferEngine
**Author:** codex
**Status:** captured

## What happened / finding

- When splitting WaferLLM Decode Attention/FFN into page-local compute entries
  and receiver-resident communication, the validated compile-only control
  chains are Attention A0–A7 and FFN F0–F3b. Every entry writes a bounded yield
  record and returns; collectives, route repaint, tasks, queues, loader and
  `decode_entry` remain absent.
- The load-bearing continuation distinction is:
  `PageControlBlock.profile_id` identifies the current entry profile, while
  `Continuation.required_profile_id` identifies the next entry profile that
  resident control must bind. Terminal A7/F3b use page/profile/entry/offset
  UNSET, remain `YIELDED`, and request `RECONFIG_Y → MARK_DONE`; resident
  control alone may later set `DONE` and then `EVICTABLE` after completion
  and queue drain.
- Command-sequence IDs are shared only for identical ordered
  operation/buffer/axis triples. Each sequence currently has at most one
  distinct non-none data buffer, so scalar `buffer_id` names that buffer (or
  zero), while the offline catalog preserves every operation triple.
- Staging an experiment that was previously represented by one untracked
  directory line changes the repository-wide porcelain hash without changing
  unrelated work. The fail-closed validator now collapses only the authorized
  `MeshJit-Decode/attention-ffn-phase1/` subtree back to its frozen sentinel
  and requires the reconstructed 112-line SHA-256
  `4dfb81759c544b9ba64810a70047a1b2a0efeecb5d6024e4fea5adc721536b54`;
  outside status and production/design hashes remain strict.
- SDK 2.10 compile-only yield fixture passed with ELF SHA-256
  `9e2c018afb824bb86c36c9dc6b6c04b090c2600beab09879eed71f2bf6c5fe3f`.
  Full M2 validation and independent Claude Code review passed. This does not
  validate compute semantics, page link closure, transfer, runtime or device
  execution.

## Implications / next actions

- [ ] Start M3 only after user acceptance: classify page-private code,
  resident code/data and unresolved DSD/DSR/profile closure without filling
  compute bodies or implementing the loader.

## Pointers

- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/STEP3_TRACKING.zh-CN.md`
- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step3-page-regions/`
- `/home/lexu/WaferLLM/MeshJit-Decode/FUNCTION_CONTAINER_DESIGN.md`
