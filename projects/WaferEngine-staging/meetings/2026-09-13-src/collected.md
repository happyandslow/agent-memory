# 2026-09-13 weekly discussion deck — collected inputs

Deck target: `../2026-09-13.pptx`, spec `deck.json` in this folder (wafer-slides pipeline).
Previous deck: `../2026-09-06.pptx` (slides 1–16 talk, 17–91 appendix).

Status: **collecting**. Le is pasting content from other sessions; nothing below
is on a slide yet. Each entry keeps the source session, the claim, the numbers
as given, and any figure/report path named.

## Inputs (in arrival order)

<!-- entry template
### N. <short label>  (source: <session/report>, received <time>)
- Claim:
- Numbers as given:
- Files / figures named:
- Open questions for Le:
-->


### 1. Layout C — implemented, measured, closed  (source: session `4b-mini-ppl-debug`, cross-session message, 2026-09-13; all 13 cited files verified present)

**One-line status (as given):** Qwen3-4B decoder layer split into three thin stages A1/A2/A3 on one 256×256 block; implemented through a first five-layer group on CS-3, measured, **closed 2026-09-13** at 3.7–3.9× the original's single-layer latency; cause structural; next = fused single block with sparse-attention logic.

**Layout figures (all under wse3-performance-model/):**
- `docs/diagrams/2026-09-13-layoutC-color-regions.png` (+ .excalidraw) — full-wafer placement: 8 groups G0–G7 (G0–G3 southbound x132–387, G4–G7 mirrored northbound x389–644), Head/Tail x3–130, 650×1028 footprint. **Analytical placement, not a compiled allocation.**
- `docs/diagrams/2026-09-10-layoutC-tall-a2.png` — one group's block geometry: A1 and A3 share left 128-wide half, A2 takes whole right 128×256 half.
- `docs/diagrams/2026-09-10-layoutC-hidden-reshard.png`, `2026-09-10-layoutC-weight-axes.png` — why row shards are 32/10/16; which tensor axis each stage shards.
- Geometry (cols × rows): A1 128×80 (hidden 32/row), spare 128×16, A3 128×160 (16/row), A2 128×256 (10/row). 65,536 PEs reserved, 63,488 active. Source of truth: `docs/reports/2026-09-13-layoutC-implementation-handoff.md` §3.

**Measured performance — real CS-3, raw device cycles, no clock assumed**
Source: `docs/reports/2026-09-13-layoutC-single-layer-performance.md`, fig `...-single-layer-performance.png`, evidence `...-evidence.json`.
Setup: batch 1, BF16, one layer, hidden 2560 / attn 4096 / KV 1024 / head 128 / FFN 9728, capacity 8192, seed-910 synthetic weights. 3 independent jobs per cell, 33 tokens each, first 4 dropped, median of 29 then median across jobs. All 1,013,760 output elements exact vs each geometry's own operation-order oracle.

| initial KV | original ATTN+FFN (256×256 + 256×256, 131,072 PE) | layout C A1+A2+A3 (65,536 PE) | ratio |
|---:|---:|---:|---:|
| 1,280 | 26,377 | 102,511 | 3.886× |
| 5,120 | 28,000 | 104,330 | 3.726× |

Boundary: START enqueue → all output rows complete, one collector PE. Empty cost 8,231/8,232 cycles, **not subtracted**. This is serialized single-layer latency — not pipelined throughput, not full-model, not trained weights. Context sensitivity: +0.42 / +0.47 cycles per KV position.

**Per-stage breakdown — CORRECTED 2026-09-13 (second message from `4b-mini-ppl-debug`)**
The earlier MAC-only breakdown (orig ATTN 560 / FFN 1,140; A1/A2/A3 = 1,536/640/3,648 MACs per PE, "explains 88–92%") is **WITHDRAWN** by its author: 4b-wide-layer showed by CS-3 measurement the kernel is comm/latency-bound, not FLOP-bound, and the MAC count names the pacing stage backwards. Struck in `docs/reports/2026-09-13-layoutC-performance-conclusion.md` §5 (kept struck); corrected reasoning in §5b. The per-PE-work bar chart (`...-per-pe-work-model.png`) is withdrawn — do not use.

Corrected content — three axes that disagree:

| stage | per-PE MACs (FLOP, derived) | per-layer TIME (measured CS-3, 2K) | per-PE SRAM (compiled, 2K) |
|---|--:|--:|--:|
| original ATTN (QKV+attn+O) | 560 | 11,886 cyc | 31.75 KB |
| original FFN | 1,140 | 5,802 cyc | 29.77 KB |

- FLOP: FFN 2× ATTN.
- **TIME: ATTN 2.05× FFN — inverted from FLOP; this is the axis that sets latency.** ATTN grows with context (T_attn/T_ffn → ~2.7 at 8K); FFN flat.
- SRAM: ATTN slightly heavier; per-PE footprint not weight-dominated.

Attribution: TIME = 4b-wide-layer's phase-TSC profile (per layer per token, 2K, full 256×256 square) — NOT the handoff doc, which only has combined single-layer numbers. SRAM = `demo/qwen3-4b-thin-stage/results/cs3/out_S1B_2K/msize.txt` (compiled totals, verified present). MACs = 4b-mini-ppl-debug's derivation.

Figure to use: `docs/reports/2026-09-13-attn-vs-ffn-three-axes.png` (verified present, 3 panels, one per axis). Viewed: bars and 2.05×/2.04×/1.07× callouts read fine at slide scale; two cosmetic defects — the FLOP panel's subtitle 'what the refuted figure plotted' collides with the y-axis 1200 tick, and the bottom footnote runs off the right edge (clipped). Either re-export from the source script before the deck, or crop the footnote and put its text in the slide caption.

**Still stands:** the 3.7–3.9× single-layer measurement; the layout geometry figures; 4b-wide-layer's separately measured result that ATTN/FFN as independent pipelined stages gives **1.47× at 2K / 1.40× at 8K**. Only the MAC-based explanation is withdrawn. (Also withdrawn with it, per conclusion doc §5/§7b: the "2.65× optimal three-way split" floor, the 0.31×/0.62× throughput figures, and the "enlarge FFN to 512×256" idea — all rested on the MAC model. Confirm with Le before citing any of them.)

**Correctness results that stand regardless** (`docs/reports/2026-09-13-layoutC-first-group-feedback.md`): first five-layer group with on-wafer feedback runs on CS-3 — mini 5 layers × 33 tokens, 10,560 elements exact; full geometry 5 layers × 2 tokens, 5,120 exact; full cache probe 83,886,080 K/V values + all cursors pass; one-bit-flip negative control fails as it should. Router-only strip transport with marker/ACK/reset/START protocol validated both directions with dropped/duplicated-fragment controls. Two device defects found and fixed 09-10 (A2 RoPE reset overwriting XKCache; cut-chain zero local-layer count) — `docs/reports/2026-09-10-layoutC-kv-fix.md`.

**Decision (Le, 09-13, as relayed):** two-group D17 link paused. Next: fused 256×256 single block, FFN+QKV on every PE, attention heavy state on 1-in-N PEs, others = KV + minimal scan. Gate = compile-only SRAM of three PE images. First-order ~1.0× original latency in half the area.

Offered but not yet pulled from that thread: state-of-play history, checker work, comm-algorithm measurements.

Slide handling notes: label the MAC table "derived model" on the slide; pipelined-throughput figures are unmeasured on both sides → dash in tables, derivation in notes (per no-uncompiled-numbers rule).

### 2. Trace length distributions, main-thread vs subagent split, on-chip KV debate conclusion  (source: session `4b-pp-demo`, cross-session message, 2026-09-13; all 6 cited files verified present)

**Where it lives:** `analyses/2026-09-12-trace-length-distributions/` (README, `plot_length_distributions.py`, `results/lengths.json`, `results/trace_length_distributions.png`); agent-memory `memory/inbox/2026-09-12-trace-length-distributions-and-subagent-vs-main.md`, `assets/2026-09-12-trace-length-distributions.png`; ContextBase doc `2026-09-12-data-request-length-distributions-of-the-three-traces-YWufPZhWnG`. Sources: gc-trace `steps.csv` (46,650 de-duplicated calls), mooncake `data/*.jsonl`, servegen `results/lengths.json`. Recomputed 2026-09-12 from existing study files.

**Per-request length distributions (tokens; p10 / p50 / p90 / p99 / max)**

| trace | n | input context | output (decode) |
|---|--:|---|---|
| Claude Code · main thread | 26,144 | 95K / 302K / 719K / 955K / 1.0M | 166 / 763 / 3.8K / 10.6K / 64K |
| Claude Code · subagents | 20,506 | 29K / 100K / 326K / 726K / 991K | 2 / 4 / 170 / 1.5K / 22.8K |
| Claude Code · all calls | 46,650 | 47K / 197K / 616K / 930K / 1.0M | 2 / 243 / 2.5K / 8.7K / 64K |
| Mooncake · conversation | 12,031 | 964 / 6.9K / 27K / 85K / 126K | 24 / 350 / 597 / 1.1K / 2,000 (cap) |
| Mooncake · toolagent | 23,608 | 1.8K / 6.3K / 17K / 62K / 126K | 3 / 30 / 507 / 897 / 2,000 (cap) |
| Mooncake · synthetic | 3,993 | 30 / 11.6K / 39K / 66K / 191K | 4 / 69 / 389 / 768 / 893 |
| ServeGen · DeepSeek-R1 | — | – / 208 / 2.1K / 23K / 57K | – / 792 / 3.4K / 12.6K / 32.8K |
| ServeGen · Qwen-Max | — | – / 812 / 2.4K / 6.2K / 31K | – / 56 / 433 / 840 / 9.3K |
| ServeGen · Qwen-Plus | — | – / 216 / 1.7K / 4.7K / 372K | – / 39 / 213 / 1.1K / 16K |
| ServeGen · Qwen-Turbo | — | – / 680 / 813 / 2.3K / 229K | – / 11 / 73 / 467 / 10.9K |

Claude Code per turn (4,032 turns): decode p50 5.8K / p90 23.5K; new prefill p50 10.9K / p90 254K. Per session (1,057): max context p50 94K / p90 281K / p99 965K. ServeGen R1: reasoning share of output p50 76 %; requests with output > 2K are 16 % of requests but 57 % of decode tokens. ServeGen publishes mean/p50/p90/p99/max only (no p10, no raw rows). Mooncake output hard-capped at 2,000.

**Claude Code: subagent calls vs main-thread calls**

| | main thread (26,144) | subagents (20,506) |
|---|--:|--:|
| input context p10 / p50 / p90 / p99 | 95K / 302K / 719K / 955K | 29K / 100K / 326K / 726K |
| first call of a session, context p50 | 51.5K | 18.6K |
| output p10 / p50 / p90 / p99 / max | 166 / 763 / 3.8K / 10.6K / 64K | 2 / 4 / 170 / 1.5K / 22.8K |
| share of calls with output ≤ 5 tokens (≤ 50) | 0.2 % (1.1 %) | 58 % (70 %) |
| output share of the class's token traffic | 11.6 % | 1.5 % |
| intra-turn gap p50 | 14.9 s | 8.3 s |
| calls per session p50 / p90 | 21 / 267 | 15 / 46 |
| output p50 by model | Opus 4.8 837 · Opus 5 673 · Fable 5 501 · Fable 5.1 1,145 | Opus 4.8 3 · Opus 5 3 · Sonnet 5 3 · Haiku 4.5 1 (p90 4) · Fable 5 74 |

- The "median context 309K" quoted in the 09-04/09-05 captures is the main-thread number; subagent calls are 44 % of all calls and including them the per-call median is 197K. (**Correction to last week's deck**, which carried 309K — flag on the slide.)
- Subagent calls are a different shape, not a smaller copy: input 3× smaller but still 10^5-scale (does not fit 29K either); output is essentially one tool call with no visible reasoning. Decode budget lives on the main thread; subagents are prefill-dominated fan-out.

**Conclusion for the on-chip KV debate ("one request's growth" vs "many parked requests")** — as given:
Three worlds, not one workload. Claude Code = huge input (p50 100–300K), medium output (per turn a few K to ~20K). Mooncake = input a few K, output a few hundred. ServeGen R1 = input a few hundred, output a few thousand. Only the agentic harness produces the "not even one fits" case: every non-agentic trace (Mooncake, all four ServeGen models) has p99 input inside the measured 29,184-token placed-region ceiling, and the whole-wafer total (29K placed + ≈74K unplaced SRAM ≈ 103K, **derived not measured**) holds tens of such sessions, whereas for Claude Code it holds a fraction of one request. So the debate has no workload-independent answer; it depends on which workload class is targeted.

Supporting measured numbers (from 09-03/09-04/09-05 captures, not new): decode cycles/step = 681K + 16 × context tokens (4K 1,005 → 29K 652 tok/s **at 750 MHz** — NOTE: canonical clock is now 0.85 GHz per Le 2026-09-07; recompute tok/s or quote cycles only); batch cycles/step ≈ 427K + 359K × bsz (asymptote ≈ 2,100 tok/s per wafer, same clock caveat); 99 % of Claude Code calls have a successor re-reading ≥ 95 % of their KV within 10–18 s; not keeping it costs a median 13.9 s reload = 61 % of the next call's latency; decode-stream concurrency p50 = 1 in both traces; single-user duty cycle 1 % per session, 8 % within a turn.

**Figure:** `analyses/2026-09-12-trace-length-distributions/results/trace_length_distributions.png` — percentile strips, log x, input + output panels, reference lines 29,184 (measured) and ≈103K (derived). Palette #2a78d6 / #d2477f / #eda100. Viewed: 2267×932, wide aspect; labels readable at slide scale, subtitle line is small — will need a `figure` slide with the subtitle text moved into the caption. The 29K/103K reference-line labels overlap slightly with the "+ unplaced SRAM" text but read.

Slide handling notes: the 103K whole-wafer figure is derived → keep it labelled derived on the slide or omit. The 750 MHz tok/s numbers conflict with the 0.85 GHz convention → quote cycles, not tok/s, unless Le says otherwise.

## Candidate slide outline (revised as inputs arrive)

(empty)

## Facts pulled from the repo to fill gaps (to list in reply, per wafer-slides rules)

(none yet)
