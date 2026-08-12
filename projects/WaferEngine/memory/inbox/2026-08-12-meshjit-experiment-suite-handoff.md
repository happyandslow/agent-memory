---
topic: meshjit-code-relocation
tags: [MeshJIT, WSE-3, remote-code-loading, multicast, TSC, prefill, chunk-size, handoff]
date: 2026-08-12
status: captured
---

## Situation

MeshJIT was evaluated as a way to reclaim per-PE SRAM by storing phase-kernel `.text` on holder PEs and moving it over the WSE-3 fabric only when needed. The immediate motivation was the PR #14 Qwen3-1.7B prefill deployment: the 512×1024 compute rectangle at chunk size 512 used 45,078 of 49,152 bytes on its tightest compute PE, leaving 4,074 bytes, while `.text` alone occupied 30,664 bytes and was the largest SRAM category.

This note is a cross-experiment handoff. The detailed 1→1 relocation and line-multicast captures have already been promoted into `memory/topics/meshjit-code-relocation.md`; this note adds the later real-kernel timing and maximum-chunk findings and records the next integration target.

## Implementations and settings

| Experiment | Implementation | Setting / measurement |
|---|---|---|
| 1→1 remote execution | `/home/lexu/MeshJIT/feasibility-demo/` | Holder PE sends a fixed-size u32 image; receiver writes an SRAM slot and calls it through `@bitcast`. Globals are pinned and DSR kinds reserved. |
| Relocated control flow | `/home/lexu/MeshJIT/controlflow-experiment/` | 40-byte forward conditional and 88-byte runtime loop; fixed 64-word receiver slot; simulator plus physical CS-3. |
| One-color line multicast | `/home/lexu/MeshJIT/broadcast-timing/` | One P-2 router path: holder `RAMP→EAST`, interior `WEST→{RAMP,EAST}`, endpoint `WEST→RAMP`; payload color 6, IQ5/OQ5 in the isolated harness. N={1,16,64,256,512}; K={64,256,1024,2048} bytes. N≤256 used 200 repetitions; N=512 used 50. |
| Real c512 function use | `/home/lexu/MeshJIT/function-use-profile/` | PR #14 geometry: batch 1, seq 8192, P=256, compute block 512×1024, 2×4 logical blocks, four layers on one representative PE, chunk size 512 (16 chunks). Exact function-body TSC intervals with an 18-cycle read-pair calibration removed. |
| Maximum chunk | `/home/lexu/MeshJIT/chunk-max-sweep/` | Isolated PR #14 commit `a8ab2a5073674ebaf3b661316ecdb5e06044f472`; production geometry unchanged; only `CHUNK_SIZE` varied. Full appliance compile/placement used for large layouts. |
| Function-size/slot extraction | `/home/lexu/MeshJIT/chunk-function-transfer/` | Exact c512/c768 linked-symbol extraction and shared-slot calculation. A physical c768 transfer run was **not** completed. |

The canonical on-device timing convention was the SDK bandwidth-test sync/ref/tic/toc protocol. Each PE samples its local 48-bit TSC at the common synchronization wave; host correction applies `ref[p] -= px+py` for the approximately one-cycle-per-hop sync-wave delay. The reported fan-out metric is `max_p(toc[p]-corrected_ref[p]) - (tic_holder-corrected_ref[holder])`. Cycle-to-time conversion uses 0.85 GHz. Host wall time is diagnostic only.

## Verified results

### Relocation correctness

- Straight-line arithmetic relocation was bit-exact in simulator and on physical WSE-3.
- A forward conditional also survived relocation to a different slot address.
- A runtime loop stalled when source and destination addresses differed, but passed in simulator and on physical WSE-3 when the receiver slot address matched the holder function address.
- Practical rule: use address-matched slots for loop/backward-branch code. Relocation of non-leaf code with helper calls remains unverified.

### Physical one-line multicast

Shortest / median cycles:

| K | N=1 | N=16 | N=64 | N=256 | N=512 |
|---:|---:|---:|---:|---:|---:|
| 64 B | 39 / 62 | 53 / 77 | 101 / 125 | 293 / 318 | 549 / 574 |
| 256 B | 93 / 150 | 107 / 168 | 155 / 214 | 347 / 406 | 603 / 662 |
| 1 KiB | 309 / 358 | 323 / 372 | 371 / 420 | 563 / 612 | 819 / 868 |
| 2 KiB | 597 / 646 | 655 / 660 | 659 / 708 | 851 / 900 | 1107 / 1156 |

Across the measured range, the shortest-cycle surface is well described by:

`T_line(N,K_bytes) ≈ 20 + 9·K_bytes/32 + (N-1)` cycles.

This is payload serialization once plus an approximately one-cycle/router-hop wavefront, rather than N payload copies. At N=512, 1 KiB costs 819/868 cycles (0.964/1.021 µs shortest/median) and 2 KiB costs 1107/1156 cycles (1.302/1.360 µs).

### Real c512 kernel body use

| Function | Linked size | Calls on profiled PE | Average exact-body cycles |
|---|---:|---:|---:|
| `rmsnorm_kernel` | 1,532 B | 128 | 3,549.13 |
| `qk_norm` | 1,936 B | 64 | 925.50 |
| `rope_kernel` | 776 B | 128 | 576.25 |
| `silu_chunk` | 1,768 B | 192 | 855.00 |
| `matmul_compute` | 876 B | 65,792 | 1,148.19 |

The calls are state-machine invocations on one representative PE, not distinct static call sites: 16 chunks × 4 layers = 64 layer-chunks; RMSNorm and RoPE run twice per layer-chunk, QK norm once, SiLU three times, and matmul runs four projections × 257 step/final calls × 64 layer-chunks. The authoritative full forward span was 430,044,189 device cycles = 505.934 ms at 0.85 GHz; the 7.047 s host run was only an end-to-end reference.

### Maximum chunk and binary growth

| Chunk | Full production-layout result | Tightest compute-PE SRAM |
|---:|---|---:|
| 512 | PASS | 45,078 B used; 4,074 B free |
| 768 | PASS, physical appliance compile/placement (`wsjob-jo69wsyn5zfd3rhwkkpfsr`) | 47,846 B used; 1,306 B free |
| 1024 | FAIL before CSL compile: KV-egress colmux DSD extent 32,768 exceeds signed-i16 maximum 32,767 | — |
| ≥1280 | Static failure: four pinned D-cache arrays require 640 B, exceeding the 512-B cap | — |

Going from c512 to c768 increased `.text` by 1,368 B (to 32,032 B), `.bss` by 1,200 B, D-cache by 128 B, and total PE use by 2,768 B. The five candidate bodies at c768 are: RMSNorm 1,792 B, QK norm 2,188 B, RoPE 788 B, SiLU 1,968 B, and matmul 888 B, totaling 7,624 B. A 32-byte-aligned shared phase slot must be 2,208 B. Removing the five bodies and adding one such slot projects 6,722 B free at c768 (`1,306 + 7,624 - 2,208`), but an integrated linked build is still required to validate that projection.

## Analysis and decisions

1. **Do not load per leaf-function invocation.** A 1–2 KiB line load is comparable to a single 500–3,500-cycle function body. MeshJIT must load at a phase/layer-chunk boundary and reuse the loaded body for all calls in that phase. Matmul is especially attractive because one resident/load event can be amortized over 257 calls per projection.
2. **Hardware line multicast is the preferred primitive.** It serializes the payload once and adds roughly one cycle per hop. Sequential unicast would replicate payload work N times; software relay/tree machinery is unnecessary for a single straight row unless required by topology or resource availability.
3. **A 2D production estimate is promising but remains a model.** For a 512×1024 comb, the longest path is about 1,534 hops. The measured line fit predicts 1 KiB at 1,842 cycles (2.167 µs) and 2 KiB at 2,130 cycles (2.506 µs), before median-mode overhead. Nine phase loads per layer-chunk over four layers and 16 chunks project to about 1.34 ms, roughly 0.27% of the 505.934-ms on-device forward span. This has not yet been measured on the full 2D rectangle.
4. **c768 is the current integration target, not the safe unmodified production setting.** The unmodified c768 build leaves only 1,306 B, while the MeshJIT projection leaves 6,722 B. Keep at least ~2 KiB final margin after the actual linked transformation; c512 remains the conservative baseline until that build exists.
5. **Fabric coexistence is unresolved.** The isolated multicast uses one payload color and one input/output queue pair. In the production prefill design, color 6 may be stage-free at useful boundaries, but all eight input and output queues are already bound. Integration therefore needs a drained repaint/rebind/fence protocol, not merely an apparently unused color.
6. **Do not report c768 transfer latency as measured.** `/home/lexu/MeshJIT/chunk-function-transfer/` contains exact c512/c768 size extraction, but no physical c768 transfer result. The line model predicts 1,152 shortest cycles for a 2,208-B slot at N=512; this is model-only.

## Next target

The next experiment should test dynamic loading of a GEMV compute unit in `/home/lexu/WaferLLM/Decode/WSE-3`, beginning with correctness in an isolated harness rather than editing the production decode path directly. Relevant source landmarks are `decode.csl` (`gemv_static_step`, `vecmat_computation`, and the projection wrappers) and `/home/lexu/WaferLLM/MeshGEMV/WSE-3/` as a standalone algorithm reference.

The offload boundary must be chosen after a call/dependency/DSD analysis. `gemv_static_step` is only one `@fmach` and is passed to `@map`, which may require a comptime function rather than a runtime function pointer. `vecmat_computation` is a more meaningful unit but is loop-bearing and closes over module globals/DSDs. Any relocated loop-bearing driver should therefore use an address-matched slot, with referenced globals and DSR reservations mirrored explicitly.

## Evidence

- `/home/lexu/MeshJIT/README.md`
- `/home/lexu/MeshJIT/broadcast-timing/results/device_summary.csv`
- `/home/lexu/MeshJIT/function-use-profile/results/device/device_8k_c512_function_profile_verdict.json`
- `/home/lexu/MeshJIT/chunk-max-sweep/{README.md,c512_baseline_sections.json,c768_sections.json}`
- `/home/lexu/MeshJIT/chunk-function-transfer/results/{c768_functions.csv,c768_symbols.json}`
- `/home/lexu/we-sram-profile/prefill_text_meshjit_candidates.md`
- ContextBase: [MeshJIT control-flow relocation](https://context.ed-aisys.com/doc/2026-08-04-result-meshjit-control-flow-relocation-sim-physical-cs-3-C0mwcg0IbD)
- ContextBase: [MeshJIT physical multicast cost + real c512 use time](https://context.ed-aisys.com/doc/2026-08-04-result-meshjit-physical-multicast-cost-real-c512-use-time-7LlgIfgzCe)
- ContextBase: [PR #14 per-PE SRAM profile](https://context.ed-aisys.com/doc/2026-08-04-result-pr-14-real-qwen3-17b-decodeprefill-per-pe-sram-profile-AzO98X7Fy2)
