# WaferEngine Plan

Human-maintained roadmap and durable progress narrative. This is the canonical home for project goals, milestones, decisions, and next actions. Generated/current status belongs in `tracking/status.md`.

## Goals

- Advance WaferEngine/WaferServe WSE-3 kernel work around qwen3-1.7B decode/prefill, especially SpecDec real-kernel integration, runtime KV loading, and PE-local SRAM/fabric limits.
- Preserve device-measured PE SRAM/resource findings so future kernel and WaferOS work uses the silicon-grounded constraints rather than stale estimates.
- Keep compile-once / serve-many serving semantics explicit: model configuration is baked into the artifact; request configuration is runtime.

## Milestones

- [x] PE SRAM/fabric resource breakdown measured on real CS-3/WSE-3; branch `lexu/pe-mem-breakdown` remains unmerged pending Le's decision.
- [x] Dynamic-KV-loading design completed for qwen3 decode; runtime KV ingress chosen over compile-time baking.
- [ ] SpecDec M1: replace the sample `passthrough.csl` oracle with real prefill + decode CSL kernels in one co-resident `SdkLayout` and verify cold-loading path.
- [ ] SpecDec M2: warm-start via host-routed KV handoff, gated on the dynamic-KV-loading decode kernel.
- [x] h2d-playground transport experiments summarized into durable docs and topic memory.
- [ ] Decide whether/how the PE-SRAM analysis should feed WaferOS/session examples and whether to merge `lexu/pe-mem-breakdown`.

## Decisions

| Date | Decision | Rationale | Link |
| --- | --- | --- | --- |
| 2026-06-28 | Trust worker-side `cs-readelf -m` coordinate data over distinct-ELF counts for PE memory variation. | Distinct ELF counts include unplaced placeholder binaries and overstate variation; coordinate truth is what sits on silicon. | `memory/topics/pe-sram-memory-breakdown.md` |
| 2026-06-28 | qwen3 decode max compile/place `MAX_SEQ_LEN` at bsz=1 is 22,784 on real WSE-3. | Compile sweep passed spp=89 and failed spp=90; ceiling is code+weights/free-SRAM, not a KV-storage choice. | `memory/topics/pe-sram-memory-breakdown.md` |
| 2026-06-30 | Use runtime KV ingress (Option B) for qwen3 decode; do not use SDK runtime symbol rebinding or memcpy transport. | Runtime symbol writes are unavailable; memcpy requires a pipeline mode/colors Le ruled out; streaming KV reuses existing mutable cache slabs and routes. | `memory/topics/dynamic-kv-load.md` |
| 2026-07-06 | Treat PR #14's model/request config split as the serving contract when/if merged. | `model_config` carries baked artifact/capacity parameters; `request_config` carries per-request `PREFILL_LEN(S)` and overlays at runtime, enabling compile-once / serve-many. | `memory/topics/dynamic-kv-load.md`; `memory/inbox/2026-07-06-pr14-real-qwen3-serving.md` |

## Next actions

- [ ] Verify live WaferEngine branch/PR state before acting; memory is context, not proof. In particular, check PR #14 (`real_qwen3_1p7`) and branches `lexu/specdec-dual-kernels` / `lexu/pe-mem-breakdown` before edits.
- [ ] For SpecDec M1, continue with decode `launch.py` real-weights reconcile + cold compile-only, then co-resident layout/device bring-up.
- [ ] On PR #14 merge, update code-facing docs to reflect that `KV_TRANSFER=0`/compile-time KV baking was deleted, and that decode rounds terminate by runtime token-path budget/EOS STOP flood.
- [ ] Add WaferOS/session examples for keeping KV cache on chip and recompute/evict behavior; recover or replace the missing Obsidian image noted in `tracking/conflicts.md`.
- [ ] Decide whether to merge `lexu/pe-mem-breakdown`; optional follow-up: run seq_len/layers-per-block sweeps.

## Narrative progress log

### 2026-07-14

- Drained `memory/inbox/2026-07-14-h2d-playground-summary.md` into `memory/topics/h2d-playground-transport.md`. Durable findings: measure device transfer with on-device TSC, pin `io_loc` for multi-stream scaling, prefer 10.27.x underlay over 100.64.x overlay, treat pipeline latency as host/network/queueing dominated, and preserve RDMA as a latency/CPU win that does not fix KV handoff. Full doc: `docs/2026-07-14-h2d-playground-experiments.md`.

### 2026-07-06

- Drained `memory/inbox/2026-07-06-pr14-real-qwen3-serving.md` into this plan and `memory/topics/dynamic-kv-load.md`. The durable facts are: PR #14 makes qwen3 serving compile-once / serve-many; splits baked `model_config` from runtime `request_config`; stages request config for device runs; removes compile-time KV bake mode (`KV_TRANSFER=0`); and uses runtime per-round budget/EOS STOP flood termination.
- Converted `memory/context.md` and `tracking/status.md` into thin generated projections that point here and to topic notes rather than repeating next-action prose.

### 2026-06-30

- SpecDec dual-kernel design recorded: M1 cold loading of real prefill/decode CSL kernels; M2 warm-start depends on dynamic KV import.
- Dynamic KV load design completed and approved for qwen3 decode.

### 2026-06-28

- PE SRAM/fabric resource analysis measured on real CS-3/WSE-3 and recorded in `memory/topics/pe-sram-memory-breakdown.md`.
