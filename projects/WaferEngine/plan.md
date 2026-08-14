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
- [ ] For future SdkLayout throughput measurements with per-step output, pre-post D2H receives before ingress so device TSC does not include host-induced output backpressure; see `memory/topics/qwen3-force-prefill-output-backpressure.md`.
- [ ] Decide whether to port the validated metadata-only prefix-0 force-prefill path from the isolated experiment snapshot into the maintained decode implementation; see `memory/topics/qwen3-force-prefill-output-backpressure.md`.
- [ ] For MeshJIT/WaferLLM SDK-2.10, restore an approved resident Decode baseline, then attempt a one-projection direct-pointer substitution with explicit ABI/DSD closure retention and receiver-ELF audit; see `memory/topics/meshjit-code-relocation.md`.
- [ ] Add WaferOS/session examples for keeping KV cache on chip and recompute/evict behavior; recover or replace the missing Obsidian image noted in `tracking/conflicts.md`.
- [ ] Decide whether to merge `lexu/pe-mem-breakdown`; optional follow-up: run seq_len/layers-per-block sweeps.

## Narrative progress log

### 2026-08-14

- Drained three 2026-08-12 MeshJIT/WaferLLM captures into
  `memory/topics/meshjit-code-relocation.md`. SDK-2.10 simulator proofs now cover both a minimal
  `cand_gemv_step` runtime-pointer body and a larger `vecmat_computation` boundary with bit-exact
  K=N=8 FP16 GEMV output. Both are feasibility results only: no physical-WSE-3 timing/SRAM claim,
  `@map` still requires comptime callbacks, and production integration needs explicit ABI/DSD/global
  closure retention plus a receiver-ELF audit.

### 2026-08-12

- Drained `memory/inbox/2026-08-11-qwen3-force-prefill-prefix0-8k.md` into
  `memory/topics/qwen3-force-prefill-output-backpressure.md`. Prefix-0 force-prefill now has a
  CS-3 measured end-to-end result at `N=F=8192`: 28-stage force reaches 34,872.31 tok/s
  device end-to-end at 0.85 GHz, **1.412× native prefill** and **2.549× 8-stage force**. The
  measurement also records that zero-prefix support requires an explicit metadata-only path in the
  adaptor/injector/block phases, not merely a relaxed host guard.

### 2026-08-11

- **Drained the paired Qwen3 force-decode-as-prefill throughput captures** into
  `memory/topics/qwen3-force-prefill-output-backpressure.md`. The 2026-08-08 late-drain
  interpretation is superseded: the host sent all teacher-forced X vectors before posting the
  output/TSC receive, so D2H backpressure entered the device-TSC interval. The corrected co-drain
  harness pre-posts the receive and restores the 28-stage advantage (N=1024: 37.4–46.9K tok/s,
  2.90–2.97× the 8-stage layout across prefixes). Device TSC can include host receive-scheduling
  stalls, so bidirectional throughput measurements must arm D2H before ingress.

### 2026-08-06

- **Drained the MeshJIT SRAM-relief captures into the new topic `memory/topics/meshjit-code-relocation.md`**
  (`memory/inbox/2026-08-04-meshjit-branch-relocation.md` + `2026-08-04-meshjit-line-multicast-cost.md`).
  Durable findings: the address-matched-slot relocation rule is **validated on silicon** (forward
  branches + straight-line code relocate freely; backward loop branches are absolute-encoded so a
  transplanted loop kernel only runs bit-exact when the receiver slot address == source); WSE-3
  router-line multicast is pipelined hardware (`T ≈ 20 + 9*K/32 + (N-1)` cycles, one hop/cycle, not
  `N*K`); real c512 phase-function sizes give a ~4,952 B shared-slot gross saving on five
  independent kernels; and per-phase reuse is promising while **per-leaf fetch is not** (load cost
  already > one body-call for qk_norm/rope/silu). Refines skill `wse-runtime-remote-code-loading`
  invariant #1.
- **Drained `memory/inbox/2026-08-04-pr14-sram-profile.md`** — its content was already folded into
  `memory/topics/pe-sram-memory-breakdown.md` § Updates 2026-08-04 (PR #14 real 2×4 re-profile);
  marked the capture drained. Headline: prefill compute PE is now the binding constraint of the
  real deployment (88.9% c256 → 91.7% c512).
- **Drained `memory/inbox/2026-08-06-qwen3-1p7b-decode-pipeline-depth-profile.md` into the
  `we-pr14-depth-layout` project** (`projects/we-pr14-depth-layout/memory/topics/decode-pipeline-depth-layout.md`
  + that project's plan), where the decode pipeline-depth experiment now lives; the capture is
  marked drained with a cross-project pointer. Headline: one-layer `64 x 256` decode fits but costs
  22.6–24.5% throughput and 42.52% max context vs the 8-stage baseline.
- **Drained `memory/inbox/2026-08-05-ssh-cs3-connection-closed-port-65535-gateway-exhaustion.md`
  into `memory/project.md` Known pitfalls** (CS-3 gateway connection-exhaustion recipe) and flagged
  it as a `cs3-run`/`cs3-runner` skill promotion candidate.

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
