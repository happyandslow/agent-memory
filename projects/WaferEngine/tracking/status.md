# WaferEngine Status

> Generated/current-state dashboard. Safe for deterministic scripts or hooks to overwrite.

Last updated: 2026-07-06 08:34 BST
Status: Active

## Summary

- **specdec on real Qwen3-1.7B kernels** (current): replace the spec-dec sample's
  `passthrough.csl` oracle with the real prefill + decode CSL kernels, co-resident
  in one `SdkLayout` (vertical stack, single load), real HF weights. Chip = draft
  model (16 drafts/round); GPU = verifier. M1 cold loading now; M2 warm-start
  (KV handoff via host route) later, gated on the dynamic-KV-loading decode kernel.
- PE SRAM memory-breakdown tool (`tools/pe_mem_breakdown/`) — built + run on CS-3
  (branch `lexu/pe-mem-breakdown`, unmerged).
  - Key result: code (`.text`) is ~half the 48 KB/PE and replicated on every compute
    PE; same-role PEs are memory-uniform; KV is the squeezed residual (seq-len ceiling
    = code+weights).
- Human WaferOS note from 2026-06-29 asks for session examples around keeping KV cache
  on chip and recompute/evict KV cache behavior.

## Current focus

- specdec dual-kernels (branch `lexu/specdec-dual-kernels`). Design:
  `docs/2026-06-30/2026-06-30-specdec-dual-kernels-design.md`. Session log:
  `memory/transcripts/2026-06-30/2026-06-30-session-specdec-dual-kernels.md`.
- M2 dependency: `docs/2026-06-30/2026-06-30-qwen3-dynamic-kv-load-design.md`
  (dynamic-KV-loading decode kernel — the runtime KV-import primitive).
- PE-SRAM breakdown analysis and WaferOS/session-example follow-up — see
  `memory/topics/pe-sram-memory-breakdown.md` and `human/2026-06-29-meeting-notes-waferos.md`.

## M1 progress (branch `lexu/specdec-dual-kernels`)

- [x] 1. Restore `integration/` modules — `bf30837` (16 files from
  `lexu/qwen-1p7b-decode-alignment@84be236`; reshard round-trip test 7/7 PASS).
- [ ] 2. Decode `launch.py` real-weights reconcile + cold compile-only.
- [ ] 3. Co-resident layout (origin-offset/namespacing adapters; one SdkLayout).
- [ ] 4. Decode round ops (rollback + `C`, RoPE table, correction inject, re-arm).
- [ ] 5. Decode round driver + cold numpy oracle.
- [ ] 6. Prefill real-weight loader + run wrapper.
- [ ] 7. `QwenDraftAppliance` (one-load + seed-token handoff) + handlers + config.
- [ ] 8. Device bring-up + verification.

## Next actions

- [ ] specdec M1 item 2 (decode launch.py real-weights reconcile).
- [ ] Add session examples of keeping KV cache on chip.
- [ ] Add session examples of recompute/evict KV cache for wafer chips.
- [ ] Decide whether to merge branch `lexu/pe-mem-breakdown` (review-clean, unmerged;
  verify live repo before action).
- [ ] Optional: config sweeps (seq_len / layers-per-block) to quantify the seq-len lever.

## Open risks/blockers

- Combined co-resident compile (two transformers, one SdkLayout) is unproven —
  retire with a compile-only check before any device run.
- EPCC cluster 502 transients on `launcher.run` (retry-able); wsjob queue can be minutes.
- Meeting note references Obsidian image `73db331c7912ebc19f99d28a36f98082.jpg`, which is
  not present in this repo; see `tracking/conflicts.md`.
- Two different dated PPTX variants now exist for the WSE per-PE resource analysis; Le
  should confirm which one is canonical before linking externally.

## Design-doc commits (this repo)

- `1e4075f` add spec · `b0cd3d4` co-residence feasible · `dcadcb2` single-load + KV
  switch · `a2ce139` reject on-chip KV, M1/M2 split.

## Recent changes (daily maintenance)

- 2026-07-06: Daily maintenance rechecked memory surfaces, TODO/human-note pointers, manual conflicts, inbox/transcript/topic indexes, and dated docs convention; no new project notes beyond existing WaferOS TODOs and manual conflicts.
- 2026-07-05: Daily maintenance rechecked memory surfaces, TODO/human-note pointers, manual conflicts, inbox/transcript/topic indexes, and dated docs convention; no new project notes beyond existing WaferOS TODOs and manual conflicts.
- 2026-07-04: Daily maintenance rechecked memory surfaces, TODO/human-note pointers, and dated docs convention; no new project notes beyond existing WaferOS TODOs and manual conflicts.
- 2026-07-01: Daily maintenance rechecked memory surfaces and TODO/human-note pointers; no new project notes beyond existing WaferOS TODOs and manual conflicts.
- 2026-06-30: Daily maintenance renamed an undated PPTX artifact to `docs/2026-06-28/2026-06-28-wse_per_pe_resource_analysis-alt.pptx` to satisfy dated-file rules without overwriting the existing dated PPTX.
- 2026-06-30: Curated the 2026-06-29 WaferOS meeting TODOs into this status and `memory/context.md`; original human note preserved.
- 2026-06-28: Device decode+prefill compiled on real WSE-3 (compile-only); per-coordinate breakdowns (329K/328K PEs) + 8 spatial heatmaps produced. Spec/plan in `docs/`; session log in `memory/transcripts/`; durable note in `memory/topics/pe-sram-memory-breakdown.md`.

## Manual conflicts / Le attention

- See `tracking/conflicts.md` for the duplicate PPTX/canonical-slide question and missing image attachment from the human meeting note.

## Freshness

- Source checked: 2026-06-30 (local project work); not rechecked by 2026-07-06 cron (memory-only maintenance)
- Memory checked: 2026-07-06 08:34 BST
- Generated by: Hermes daily maintenance
