# PE SRAM Memory Breakdown (qwen3-1.7B decode + prefill, real WSE-3)

## Summary

Per-PE 48 KB SRAM breakdown (code / weights / KV / activations / system / free) for the
qwen3-1.7B decode and prefill kernels, measured on the real CS-3 (WSE-3) fabric. Headline:
`.text` (the full transformer-layer program) is **~half the entire 48 KB and is replicated on
every compute PE** — the #1 cost, ahead of weights (~11 KB). KV cache is the squeezed residual
(<0.4 KB/PE), so **max-seq-len is capped by code+weights, not by a KV-storage choice**. Tool:
`tools/pe_mem_breakdown/` (branch `lexu/pe-mem-breakdown`, NOT merged).

## Current state

Measured 2026-06-28 on real CS-3 (762×1172, cmaddr 10.27.29.3:9000), `--compile-only` (random
weights — memory layout is weight-value-independent). Coordinate ground-truth via worker-side
`cs-readelf -m` → `msize.txt` → `run_breakdown.py --msize-file` (decode 329090 placed PEs,
prefill 327938).

Per compute PE (of 48 KB), PE-weighted coordinate truth:

| role | code | weights | KV | activ | system | free | %used |
| --- | --: | --: | --: | --: | --: | --: | --: |
| decode (compute) | 22.6K | 11.2K | 0.23K | 0.38K | ~3.6K | ~11K | 77–79% |
| prefill (compute) | 23K | 11.2K | 0.35K | 0.40K | ~5.4K | ~8.4K | ~82% |
| ht_head (embedding) | 2.2K / 1.0K | 19K / **38K** | 0 | 0 | ~1.2–1.6K | 26K / 8.9K | 46% / 82% |
| ht_tail (lm_head) | 9.0–9.3K | 19K | 0 | ~0 | ~6.5K | ~14K | ~70% |

(ht_head/ht_tail two numbers = decode / prefill; prefill ht_head embedding is structural/mock so
its 38 KB is the as-built footprint.) demux/mux/io_port are routing-only (~0–64 B code).

**SAME-ROLE PEs ARE MEMORY-UNIFORM on silicon** (verified over every placed PE):
- Prefill: every role BYTE-IDENTICAL (Δ=0, σ=0) — all 262144 prefill PEs = exactly 40720 B.
- Decode: uniform except the `decode` role has a 544 B (1.4%) two-class split, entirely in
  `system`/routing, exactly half-and-half = **row_0 vs row_1**; code & weights identical.
- ⇒ Stacked-bar means need NO error bars; the mean is the per-PE value (decode ±0.7%).

## Max sequence length (measured on real WSE-3, bsz=1, decode)

`integration/probe_seqlen_device.py` sweeps MAX_SEQ_LEN (compile-only, one wsjob, catches the
RuntimeError SdkLauncher raises on a placement OOM; keep MAX_OUTPUT_LEN≥15 to avoid the unrelated
short-egress OOM). **Result: MAX_SEQ_LEN = 22,784 (seq_len_per_pe=89) is the max that compiles +
places; 23,040 (spp=90) OOMs.** That's 44.5× the shipped 512 — qwen3-1.7B (unlike llama-8B, which
is pinned at spp=2 by its ~29 KB .bss) has real KV headroom because its compute PE is only ~38 KB
used / ~11 KB free.

Mechanism (matches llama failure mode, just ~45× later): KV grows ~112 B/PE per spp step (= per
256 tokens ⇒ **0.4375 B/token/PE** at bsz=1). The ~10.9 KB free fills until ~1 KB remains, which the
`.task_table`/`.data.hi` placement needs → OOM. Analytical predicts ~spp 90–91; measured spp=89.
NOTE: this corrected the tool's `bytes_per_token_per_pe` (was returning the per-256-token-step value
112, now 112/256; added `bytes_per_seqstep_per_pe`). Caveat: compile/fit ceiling, not a verified
full inference run; bsz=1 (KV ∝ batch).

Full compile sweep (real WSE-3, `test_device_2x2blk.json`, PREFILL_LEN=256, MAX_OUTPUT_LEN=64):

| MAX_SEQ_LEN | seq_len_per_pe | result |
| --: | --: | --- |
| 512 (shipped) | 2 | PASS |
| 1,024 | 4 | PASS |
| 2,048 | 8 | PASS |
| 4,096 | 16 | PASS |
| 8,192 | 32 | PASS |
| 16,384 | 64 | PASS |
| 20,480 | 80 | PASS |
| 22,528 | 88 | PASS |
| **22,784** | **89** | **PASS ← max** |
| 23,040 | 90 | FAIL (per-PE OOM) |
| 24,576 | 96 | FAIL |
| 32,768 | 128 | FAIL |

Method notes: geometric bracket (1024→32768) then binary-narrow; sweep many MAX_SEQ_LEN per wsjob
to save cluster time. EPCC 502 transients (`_InactiveRpcError ... status 502`) on `launcher.run`
killed the appliance session mid-sweep (every later config inherits the dead connection) — these are
NOT real OOMs; the driver/reader must distinguish them from the real OOM signature
(`RuntimeError: SdkLauncher.run() command error`) and re-run the affected range in a fresh session.
Two more caveats on the 22,784 figure: (1) it's the compile/placement ceiling — a full inference run
at that length was NOT executed; (2) bsz=1 — KV scales linearly with batch, so 2 concurrent requests
≈ halve the max length.

## Colors — the second scarce per-PE resource (24 fabric channels)

A color is "in use" in a step when code binds it to `@fabin`/`@fabout`. Static per-role analysis
(`color_usage_map.py`), color IDs from `colors.json`:
- **Decode compute PE: 8/24 colors** (16 free on this PE). All matmuls go through **all-reduce**, so
  colors **1–5** are time-multiplexed and **repainted 6×/layer** by `reconfig_allreduce_axis()`
  (`decode.csl:1213/1227/1233/1239/1252/1258`) — switching the collective between **Y / X / kv-head
  BAND**. "Free" colors aren't wasted: kpipe 7–17 = strip PEs, 18/21/22/23 = ht_head/ht_tail.
- **Prefill compute PE: 17/24 colors** (7 free). Matmuls use **systolic MeshGEMM** with 6 dedicated
  **statically-routed** hop colors (6–11), never repainted mid-matmul; plus reduces (1–5), KV-hops
  (17–19), shuttles (3–4/12–13).
- **Trade-off:** decode = color-frugal / reconfiguration-heavy (route-repaint cycles to save colors);
  prefill = color-hungry / reconfiguration-light (colors to keep matmul routes static). Neither is
  color-bound. Full write-up + traceability: `../../docs/2026-06-28/2026-06-28-wse-per-pe-resource-discovery.md`;
  slides `../../docs/2026-06-28/2026-06-28-wse_per_pe_resource_analysis.{pptx,pdf}`.

## Decisions

| Date | Decision | Rationale | Link |
| --- | --- | --- | --- |
| 2026-06-28 | Trust `--msize-file` (coord) over `--elfs-only` for "how many PEs look like X" | `--elfs-only` counts distinct binaries in `executables/`, INCLUDING unplaced placeholder binaries (e.g. decode-259/269, ~7.7 KB .text) that never sit at a real coordinate — it OVERSTATES variation | — |
| 2026-06-28 | **CORRECTION:** no large central-vs-edge / interior-vs-strip decode variation | Coordinate `cs-readelf -m` shows every real decode PE at total 37728/38272 (~77–79%); the "strip 45%" claim was an `--elfs-only` artifact | supersedes earlier session note |
| 2026-06-28 | Get device per-coordinate totals by running `cs-readelf -m` WORKER-SIDE | Device `sim.elf` is >2 GB → `download_artifact` exceeds the 2 GB gRPC cap; but `launch.py` runs inside the SDK container (via cs_python) so `cs-readelf` is on PATH and writes a tiny `msize.txt` to pull | — |
| 2026-06-28 | seq-len ceiling is code+weights, not KV | Compute PEs are ~77–82% full with KV already sub-0.4 KB; grow seq-len by cutting code/weights (fewer layers/block, quantized FFN), not "more KV room" | confirms `WaferServe/.../PE_SRAM_BREAKDOWN.md` on silicon |
| 2026-06-28 | qwen3 decode max MAX_SEQ_LEN (bsz=1) = **22,784** on real WSE-3 (44.5× the shipped 512) | measured by `integration/probe_seqlen_device.py` compile sweep; spp=89 PASS, spp=90 OOM; qwen3's light ~11 KB-free PE gives real KV room (llama-8B doesn't) | see Max-sequence-length section |

## Commands / paths

```bash
# Quick per-distinct-ELF breakdown (no cluster sim.elf; OVERSTATES variation — placeholders):
python tools/pe_mem_breakdown/run_breakdown.py --artifact <dir> --kernel decode \
    --config <cfg.json> --out <out> --elfs-only

# Ground-truth per-coordinate (needs msize.txt from worker-side cs-readelf -m):
python tools/pe_mem_breakdown/run_breakdown.py --artifact <dir> --kernel decode \
    --config <cfg.json> --out <out> --msize-file <dir>/msize.txt
# then the 8 spatial maps placed by coordinate:
python tools/pe_mem_breakdown/heatmaps_from_csv.py --csv <out>/decode_breakdown.csv \
    --out <out>/heatmaps --kernel decode

# Device compile + pull (via cs3-runner skill), worker-side msize:
#   launch_device.py --compile-only  ->  pulls executables/+sim.map+plan.json+msize.txt
#   (msize.txt written by launch.py compile_only: cs-readelf -m sim.elf inside the SDK container)
```

Results committed at `tools/pe_mem_breakdown/results/{decode,prefill}/` (per-coord CSV + stacked
+ within_block + `heatmaps/` with the 8 maps). Raw device ELFs in `device_artifacts/` (gitignored;
reproducible). Fabric layout: thin HT band x≈4–131 (x_demux, ht_head y<256, ht_tail y≥256, mux,
io_port) + compute block x≈132–644. Weights concentrate in the HT band; kv/activ/rope only in the
compute block.

## Open questions

- Branch `lexu/pe-mem-breakdown` not merged (per user). 17+ commits, review-clean.
- Config sweeps (seq_len / layers-per-block) to quantify the seq-len lever — not yet run.

## Last updated

2026-06-28

## Related

- `tools/pe_mem_breakdown/` (the tool); design+plan at `projects/WaferEngine/docs/2026-06-28/pe-sram-memory-breakdown-tool-{design,plan}.md`; full session log at `projects/WaferEngine/memory/transcripts/2026-06-28/session-multi-request-brainstorm.md`.
- Earlier hand-analysis: `WaferServe/kernels/Decode-GQA/docs/PE_SRAM_BREAKDOWN.md`,
  `PE_MEMORY_ANALYSIS.md` (this supersedes them on silicon, both phases).
- `csl_cs_python_cwd_binding` — cs_readelf/cs_python SIF binds only $PWD.
- decode worker seq-len ceiling (spp=2 fits / spp=4 OOMs) — same root cause.
