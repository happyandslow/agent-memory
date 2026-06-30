# 2026-06-30 — specdec on real Qwen3-1.7B kernels (dual-kernel, co-resident)

## Goal
Replace the spec-dec sample's `passthrough.csl` oracle with the real Qwen3-1.7B
prefill + decode CSL kernels, co-resident in one `SdkLayout` (vertical stack,
single compile+load), real HF weights on both. Add the on-chip spec-dec **DRAFT
model** round op to the decode kernel. Chip = draft model (generates 16 drafts/
round); external GPU = target/verifier.

## Design
Spec doc: `agent-memory/projects/WaferEngine/docs/2026-06-30/2026-06-30-specdec-dual-kernels-design.md`
(mirror in `research/notes/daily/research/superpowers/2026-06-30-specdec-dual-kernels-design.md`).

Key decisions:
- **Co-resident, single load, no reload.** Two 512×512 kernels DON'T fit side by
  side (>762 wide) but DO stack vertically (514+514 < 1172). One SdkLayout via the
  origin-offset/namespacing adapters.
- **On-chip KV transfer investigated → REJECTED.** Prefill/decode use transposed
  KV sharding (seq X-blocked vs Y-round-robin, K-dim interleave); on-chip needs a
  new fabric grid-transpose reshard with no primitive — strictly harder than the
  host route, which already has that reshard in numpy (`device_reshard.kv_to_device`).
- **Two milestones.** M1 cold loading now (seed-token handoff, zero KV, real
  weights). M2 warm-start later via host route (`memcpy_d2h` prefill `K/V_cache_bank`
  → unshard → reshard → dynamic KV load) gated on the separately-built
  dynamic-KV-loading decode kernel.

### Design-doc commits (agent-memory repo)
- `1e4075f` — add specdec dual-kernels design spec
- `b0cd3d4` — fix: co-residence feasible (vertical stack), not forbidden by geometry
- `dcadcb2` — co-resident single-load + KV-only switch (warm)
- `a2ce139` — reject on-chip KV transfer; restructure to M1 cold / M2 warm

## M1 work breakdown (code: branch `lexu/specdec-dual-kernels` off `main`)
- [x] **1. Restore `integration/` modules** — `bf30837`. Canonical 16-file package
  restored from `lexu/qwen-1p7b-decode-alignment@84be236` (had been deleted; only
  `_staging`/`_runs` survived). M1-critical: `hf_weights.py`, `device_reshard.py`,
  `prefill_kv_unshard.py`, `run_pipeline.py`. All 16 byte-compile.
- [ ] 2. Reconcile decode `launch.py` real-weights path + cold-start compile-only.
- [ ] 3. Co-resident layout (origin-offset + namespacing adapters; one SdkLayout).
- [ ] 4. Decode kernel round ops (rollback + `C` state, RoPE position table,
  correction inject, per-round re-arm, forever loop).
- [ ] 5. Decode round driver + cold numpy oracle.
- [ ] 6. Prefill real-weight loader `prefill_device_reshard.py` + run wrapper.
- [ ] 7. `QwenDraftAppliance` (one-load + seed-token handoff) + handlers + config.
- [ ] 8. Device bring-up + verification (≥2-request no-reload handoff; multi-round).

## Notes
- Recovered prior context: deleted `kernels/*_adapter.pyc` (co-resident scaffolding,
  stubs) and deleted top-level `integration/*.py` (real-weight chain, device-proven
  CHAIN PASS 2026-06-13 `decode-gpu-kv` tokenmatch).
- Prefill retains full KV (`K/V_cache_bank` are `export var`) but the `kv_drain`
  egress is a contract, not yet implemented — M2 item.
