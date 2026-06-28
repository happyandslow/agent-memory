# 2026-06-28 — PE SRAM memory-breakdown tool + real-device decode/prefill analysis

## Goal
Understand how a single LLM is served on the WSE today; build a systematic, repeatable
tool that produces a per-PE SRAM memory breakdown (code / weights / KV / activations /
system / free) for a compiled CSL artifact, and run it on the real CS-3 chip for
qwen3-1.7B decode and prefill.

## Deliverable: `tools/pe_mem_breakdown/` (branch `lexu/pe-mem-breakdown`)
Built via brainstorming → spec → plan → subagent-driven execution (9 code tasks + final
whole-branch review, 28 tests). Spec/plan in `/home/lexu/agent-memory/projects/WaferEngine/docs/2026-06-28/pe-sram-memory-breakdown-tool-{design,plan}.md`.

- `pe_mem/elf_parse.py` — `readelf -SW/-sW` → section + symbol byte sizes.
- `pe_mem/cs_readelf.py` — `cs_readelf -m` per-coordinate totals (SIF binds only $PWD → run cwd=artifact_dir).
- `pe_mem/simmap.py` — `sim.map` region boxes; `coord_role` (smallest-area, excludes whole-fabric `default_elf`).
- `pe_mem/categorize.py` — symbol-driven 6-category classifier; weights/KV/activations from `.bss` symbols; CSL runtime/DSD/routing symbols fold into `system`; RoPE = labeled sub-bucket of weights. Hard reconciliation: code+weights+kv+activations+system+unclassified == total.
- `pe_mem/extract.py` — artifact → per-coordinate rows (coord→ELF join by region + nearest section-total); `extract_from_elfs` = per-distinct-ELF mode (no cs_readelf/sim.elf/coords).
- `pe_mem/plot.py` — fabric heatmap + per-role stacked + within-block code/total spread + headroom. Heatmap skipped when no coords.
- `pe_mem/kv_cost.py` — first-order KV bytes/token/PE.
- `run_breakdown.py` — CLI (`--elfs-only`, `--msize-file`). `compile_on_cs3.md` + `pull_artifact.sh`.

Validated on local sim fixture (`out_perfunc`): 400 PEs, 0 reconciliation failures, 0 unclassified.

## Device run (CS-3 WSE-3, real fabric 762×1172, cmaddr 10.27.29.3:9000)
- Exposed `--compile-only` on decode `launch.py` (prefill already had it) + `--compile-only` +
  `download_artifact` on both `launch_device.py`.
- **Gotcha:** `download_artifact("out_device")` of the whole dir fails — tarball >2 GB (gRPC cap)
  because of `sim.elf`/`out.core`. Fix: pull only `executables/` + `sim.map` + `plan.json` (small).
- Compile-only (random weights; memory layout is weight-value-independent): decode 37 s, prefill 42 s.
- Pulled small files (base64-over-ssh tar), ran `--elfs-only`. 0 reconciliation failures, 0 unclassified
  on both. Decode 271 distinct ELFs, prefill 291.

### Decode (28 layers, seq 512, P_BLOCK_SIZE=256) — bytes of 48 KB/PE
| role | code | weights | KV | activ | system | free | %used |
|---|--:|--:|--:|--:|--:|--:|--:|
| decode — interior | ~22.6K | 11227 | 227 | 273 | 3688 | ~10.3K | ~79% |
| decode — edge/strip | ~7.7K | 11224 | 224 | 16 | ~3.0K | ~27K | ~45% |
| ht_head (embedding) | 2220 | 19008 | 0 | 0 | 1740 | 26184 | 47% |
| ht_tail (lm_head) | 9301 | 19024 | — | 4 | 6772 | 14051 | 71% |
KV headroom (interior, first-order): ~10 KB free / 112 B-per-token ≈ ~89 extra tokens.

### Prefill (single region, 4 logical blocks)
| role | code | weights | KV | activ | system | free | %used |
|---|--:|--:|--:|--:|--:|--:|--:|
| prefill | ~23.0K | 11200 | 352 | 396 | 5563 | ~8.2K | ~82.5% |
| ht_head (struct. embed) | 1008 | 37988 | 0 | 64 | 1592 | 8490 | ~82.7% |
| ht_tail (lm_head) | 9004 | 19008 | — | 4 | 6726 | 14410 | 71% |
Intra-block uniform (code swing ~664 B); no strip-column class like decode.

## Key findings (the disaggregated-memory tax, confirmed on silicon)
1. **Code (`.text`) is ~half the 48 KB SRAM (~22–23 KB) and is replicated on every compute PE** — the
   full transformer-layer program, paid ~65K times. It's the #1 consumer, ahead of weights (~11 KB).
2. **Both kernels run ~80–83 % full on their busy PEs.** Decode interior 79 % (10 KB free); prefill 82.5 %
   (8 KB free). Prefill is tighter — bigger `system` (causal mask + V-stash + MeshGEMM comm buffers).
3. **Central-vs-edge is real and large on decode:** interior compute PEs 79 % vs west/east K-pipe strip
   columns ~45 %. Prefill is uniform.
4. **KV cache is tiny (<0.4 KB/PE) but it's the binding constraint for seq-len.** Busy PEs have only
   ~8–10 KB free; max-seq-len can't grow without first cutting code or weights (fewer layers/block,
   quantized FFN banks) — matches the earlier hand-analysis (`WaferServe/.../PE_SRAM_BREAKDOWN.md`),
   now confirmed across both phases on real hardware.
5. `ht_head`/`ht_tail` are weight-bound (19 KB embedding / lm_head shards; prefill ht_head 38 KB struct).

## Results artifacts
`tools/pe_mem_breakdown/results/{decode,prefill}/` — CSV + stacked + within_block PNGs (committed).
Raw device ELFs in `device_artifacts/` (gitignored; reproducible via `launch_device.py --compile-only`).

## Open / next
- Branch `lexu/pe-mem-breakdown` NOT merged (per user). 17+ commits, review-clean.
- Deferred minors (final review): plot unused `bytes_per_token` param; broad `_SYS_SYMS` fragments.
- Possible follow-ups: PE-count-weighted role means (interior dominates, so unweighted decode mean
  understates); spatial heatmap on device (needs cs_readelf -m on the worker-side sim.elf, or plan.json
  coord parsing); config sweeps (seq_len / layers-per-block) to quantify the seq-len lever.

## Correction (end of session) — no central-vs-edge decode variation
The earlier "decode interior 79% vs edge/strip 45%" claim (rows above) is an **artifact** and is
WRONG. It came from `--elfs-only`, which counts distinct binaries in `executables/` INCLUDING
unplaced placeholder ELFs (decode-259/269, ~7.7 KB .text) that never sit at a real coordinate.
The coordinate ground-truth (`cs-readelf -m`, `--msize-file`) shows **same-role PEs are
memory-UNIFORM**: every prefill PE byte-identical (40720 B); decode uniform except a 544 B (1.4%)
`system`-only split = row_0 vs row_1. So stacked-bar means need no error bars, and there is no
large interior-vs-strip story. Trust `--msize-file` over `--elfs-only`. (Curated into
`projects/WaferEngine/memory/topics/pe-sram-memory-breakdown.md`.)
