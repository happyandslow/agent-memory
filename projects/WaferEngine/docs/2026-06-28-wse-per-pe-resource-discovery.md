# WSE-3 per-PE resource analysis — discovery write-up (qwen3-1.7B)

**Date:** 2026-06-28
**Repo / branch (all code + image artifacts):** `WaferEngine` @ `lexu/pe-mem-breakdown` (NOT merged)
**Tool:** `tools/pe_mem_breakdown/`  ·  **Hardware:** real Cerebras CS-3 (WSE-3, fabric 762×1172, `cmaddr=10.27.29.3:9000`)
**Slides:** `projects/WaferEngine/docs/wse_per_pe_resource_analysis.{pptx,pdf}` (this repo) · regen `make_slides.py`
**Curated short note:** [`memory/topics/pe-sram-memory-breakdown.md`](../memory/topics/pe-sram-memory-breakdown.md)

Image paths below are **WaferEngine-repo-relative** (`tools/pe_mem_breakdown/results/…`) on branch
`lexu/pe-mem-breakdown`; the "added in" commit makes each traceable.

---

## 0. The question

A GPU has shared HBM; the WSE has **disaggregated memory** — ~900K PEs, each with its own **48 KB
SRAM**, nothing shared. Running an LLM means **replicating the program** on every PE and **sharding the
weights** across them, leaving little room for KV cache. There is a *second* scarce per-PE resource:
the **24 fabric "colors"** (routing channels). We built a tool to X-ray a single PE's use of both, and
ran it on real silicon for qwen3-1.7B **decode** and **prefill**.

## 1. Method (and the gotchas that mattered)

- `launch_device.py --compile-only` on a real wsjob (random weights — the memory layout is
  weight-value-independent): decode compile 37 s, prefill 42 s.
- **Whole-artifact download fails** (`download_artifact("out_device")` → >2 GB gRPC cap, because of
  `sim.elf`/`out.core`). Fix: pull only `executables/` + `sim.map` + `plan.json`. *(commits `577210f`,
  `17dcf35`, `4a9b2e8`)*
- For true **per-coordinate** placement, `sim.elf` is also >2 GB. Fix: run `cs-readelf -m`
  **worker-side inside `launch.py`** (it runs in the SDK container, so `cs-readelf` is on PATH) and
  download only the tiny `msize.txt`. decode 329,090 PE coords, prefill 327,938. *(commits `bd8eb25`,
  `2813f48`, `37d945c`)*
- `run_breakdown.py --msize-file` does the coord→ELF join over ~329K PEs (~63 s); reconciles to the
  byte (0 failures, 0 unclassified). EPCC **502 transients** on `launcher.run` masquerade as failures —
  distinguish from real OOM (`RuntimeError: command error`).
- Insight that kills the "many PEs" scale worry: results are **per-role static** (every PE of a role is
  identical), so it's ~6 role-classes, not 329K.

## 2. Finding 1 — code eats half of every PE; KV is the residual

Per compute PE (of 48 KB), PE-weighted coordinate truth:

| | code | weights | KV | activ | system | free | %used |
|---|--:|--:|--:|--:|--:|--:|--:|
| decode PE | 22.6K | 11.2K | 0.23K | 0.38K | ~3.6K | ~11K | ~77–79% |
| prefill PE | 23K | 11.2K | 0.35K | 0.40K | ~5.4K | ~8.4K | ~82% |
| ht_head | 2.2K/1.0K | 19K/**38K** | 0 | 0 | ~1.2–1.6K | 26K/8.9K | 46%/82% |
| ht_tail | 9.0–9.3K | 19K | 0 | ~0 | ~6.5K | ~14K | ~70% |

- **`.text` (the full transformer-layer program) is ~half the 48 KB and is replicated on every compute
  PE** — the #1 cost, ahead of weights. KV is the squeezed residual (<0.4 KB/PE).
- **Same-role PEs are memory-uniform on silicon** (verified over every placed PE): prefill byte-identical
  per role; decode uniform except a 544 B (1.4%) `system`/routing split = row_0 vs row_1.
- **Correction recorded earlier:** there is NO large "central-vs-edge" decode variation — that was a
  `--elfs-only` artifact (it counts unplaced placeholder binaries). The `--msize-file` coord path is truth.

Images *(added in `33ecf27` decode, `95b66b8` prefill)*:
- per-role stacked: `tools/pe_mem_breakdown/results/decode/decode_stacked.png`, `…/prefill/prefill_stacked.png`
- 8-field spatial heatmaps: `…/results/decode/heatmaps/decode_heatmaps_all.png` (+ per-field), `…/prefill/heatmaps/prefill_heatmaps_all.png`

## 3. Finding 1b — placement on the 2-D fabric

The kernel is laid out as functional blocks: a thin **HT band** (x≈4–131: x_demux, ht_head y<256,
ht_tail y≥256, mux/io_port) + the big **compute block** (x≈132–644: the 2×2 logical decode/prefill
blocks). Weights concentrate in the HT band; KV/activations/rope only in the compute block.

Images *(added in `cb1e81f`)*: `…/results/decode/decode_placement_map.png`, `…/results/prefill/prefill_placement_map.png`

## 4. Finding 2 — max sequence length = 22,784 tokens (44.5× the shipped 512)

`integration/probe_seqlen_device.py` *(commit `023cf1d`)* sweeps `MAX_SEQ_LEN` (compile-only, one wsjob;
`MAX_OUTPUT_LEN≥15` avoids the unrelated short-egress OOM):

| MAX_SEQ_LEN | seq_len_per_pe | result |
|--:|--:|---|
| 512 (shipped) | 2 | PASS |
| 16,384 | 64 | PASS |
| 22,528 | 88 | PASS |
| **22,784** | **89** | **PASS ← max** |
| 23,040 | 90 | FAIL (per-PE OOM) |

qwen3-1.7B (unlike llama-8B, pinned at spp=2 by its ~29 KB `.bss`) has real KV room because its compute
PE is only ~38 KB used. KV grows ~0.4375 B/token/PE; the ~11 KB free fills until ~1 KB remains (needed
for `.task_table`/`.data.hi` placement) → OOM. This also corrected the tool's `bytes_per_token_per_pe`
(was per-256-token-step; now per-token) *(commit `37d75bb`)*. **Caveats:** compile/fit ceiling (no full
inference run at that length); bsz=1 (KV ∝ batch). Recorded in topic note *(agent-memory `b4f0205`)*.

## 5. Finding 3 — "colors" are the other scarce resource

24 fabric colors = communication channels; a color is "in use" in a step when code binds it to
`@fabin`/`@fabout`. Static per-role analysis (`color_usage_map.py`):

- **Decode compute PE: 8/24 colors used (16 free on this PE).** It does every matmul via **all-reduce**,
  so colors **1–5** are the workhorses, **repainted 6× per layer** by `reconfig_allreduce_axis()`
  (`decode.csl:1213/1227/1233/1239/1252/1258`) to switch the collective between **Y-axis / X-axis /
  kv-head BAND** reductions. The "free" colors aren't wasted — kpipe 7–17 belong to strip PEs, 18/21/22/23
  to ht_head/ht_tail.
- **Prefill compute PE: 17/24 colors used (7 free).** Its matmuls use **systolic MeshGEMM** with 6
  dedicated **statically-routed** hop colors (6–11), never repainted mid-matmul, plus reduces (1–5),
  KV-hop colors (17–19), and block shuttles.
- **The trade-off:** decode = *color-frugal, reconfiguration-heavy* (spends route-repaint cycles to save
  colors); prefill = *color-hungry, reconfiguration-light* (spends colors to keep matmul routes static).
  Neither kernel is color-bound today.

Images *(created `bf7a769`, reconfig-aware final `0869200`)*:
`…/results/decode/decode_color_usage.png`, `…/results/prefill/prefill_color_usage.png`

Medium-confidence cells (verify vs `comm_pe.csl` if exactness needed): prefill kv_drain 17–19 timing,
softmax color subset, exact band-reduce subset.

## 6. Traceability summary

| Artifact | WaferEngine path (branch `lexu/pe-mem-breakdown`) | added in |
|---|---|---|
| tool | `tools/pe_mem_breakdown/` (`run_breakdown.py`, `heatmaps_from_csv.py`, `placement_map.py`, `color_usage_map.py`) | `980ffd1`..`0869200` |
| decode stacked + heatmaps + CSV | `results/decode/…` | `33ecf27` |
| prefill stacked + heatmaps + CSV | `results/prefill/…` | `95b66b8` |
| placement maps | `results/{decode,prefill}/*_placement_map.png` | `cb1e81f` |
| color-usage maps | `results/{decode,prefill}/*_color_usage.png` | `0869200` |
| seq-len probe | `models/qwen3_1p7b-decode/integration/probe_seqlen_device.py` | `023cf1d` |
| device enablement (compile-only, msize) | `models/qwen3_1p7b-{decode,prefill}/launch*.py` | `38580db`,`577210f`,`17dcf35`,`bd8eb25`,`2813f48`,`37d945c` |
| slides (this repo) | `projects/WaferEngine/docs/wse_per_pe_resource_analysis.{pptx,pdf}` | agent-memory |

Raw device ELFs/`msize.txt` are gitignored (`tools/pe_mem_breakdown/device_artifacts/`, reproducible).
Spec + plan: `projects/WaferEngine/docs/2026-06-28-pe-sram-memory-breakdown-tool-{design,plan}.md`.
Full session log: `projects/WaferEngine/memory/transcripts/2026-06-28-session-multi-request-brainstorm.md`.
