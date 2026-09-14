# 2026-09-13 weekly discussion deck — collected inputs

Deck target: `../2026-09-13.pptx`, spec `deck.json` in this folder (wafer-slides pipeline).
Previous deck: `../2026-09-06.pptx` (slides 1–16 talk, 17–91 appendix).

Status: **draft v1 built 2026-09-14** (`deck.json` → `../2026-09-13.pptx`, 54 slides, validator OK). See `EDITING.md` for what is pending Le. Each entry keeps the source session, the claim, the numbers
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

### 3. Strategic analyses — GPU baseline, capacity vs traces, multi-card, interconnect correction, industry context, positioning  (source: session `4b-wide-layer`, cross-session message, 2026-09-13; Rounds 153–164 of `docs/reports/2026-09-04-4b-wide-layer-session-report.md` (verified present, rounds located at lines 8559–9426+) and artifact https://claude.ai/code/artifact/52cee6ad-bc9a-4883-bcbc-dfd2b98fe338. Author labels each item measured / derived / retracted.)

**3.1 GPU baseline (measured both sides)** — `docs/reports/2026-09-13-sglang-qwen3-4b-h100-baseline.md` (SGLang 0.5.19, 1× H100 80GB, vanilla, every cell measured; verified present).

| | CS-3 | H100 80GB | |
|---|--:|--:|---|
| decode bs=1 @4K | ~1,000 tok/s (1.0 ms) | 213 (4.70 ms) | CS-3 4.7× |
| decode bs=1 @~30K | 653 | 162 | CS-3 4.0× |
| context slope | 21.5 ns/token | 48.9 ns/token | CS-3 2.3× shallower |
| decode, batched | ~2,100 | 4,684 (bs32@1K) | H100 2.2× |
| prefill (native) | 9.3–9.8K | 66.5–70.4K | H100 ~7× |
| max context, 1 request | 29K | ~524K | H100 18× |

⚠ CLOCK: the CS-3 column (~1,000 / 653 / ~2,100 tok/s, 1.0 ms, 21.5 ns/token) matches the 750 MHz conversion (681K+16×4K = 745K cyc → 1,007 tok/s at 0.75 GHz; 1,141 at 0.85 GHz). Le's rule (2026-09-07) is 0.85 GHz. At 0.85 GHz the ratios vs H100 become ~5.4× / 4.5× / 2.6× shallower / H100 batched 2.0× / prefill ~6×. **Ask Le which clock the deck uses before tabulating; the H100 side is unaffected.**

- Confirmed: finding 10 goes from extrapolated to measured — prefill is ~7× behind.
- Killed: the "fast recompute engine for short-context multi-tenant traffic" claim. Even the analytical thin-stage 31–43K forced prefill is 1.6–2.2× slower than H100's measured native prefill. No prefill-side wedge on the roadmap.
- Sharpest sentence: the only measured advantage (single-stream decode, 4.0–4.7×, growing with context) applies exclusively to the workload whose context cannot be held. Median agentic turn at short context: CS-3 6.9 s vs H100 28 s. At the real 197K context: H100 ~75 s, CS-3 cannot hold it.

**3.2 Capacity case does not survive the traces (derived ladder vs measured traces)**
Claude Code all calls p10 47K / p50 197K / p90 616K / p99 930K. Mooncake p99 62–85K; ServeGen p99 ≤23K. Far-pool analytical ceiling 167K (every lever built) sits below the 197K median. No rung reaches the agent harness: fusion ~17.6K, split ~26K, near pool 95K, far pool 167K (all analytical). Workloads that do fit (Mooncake/ServeGen) also fit in 80 GB HBM.
> "Capacity cannot reach the workload that wants it; the workloads it reaches do not need it."
Reopener: 167K is the score-buffer wall, not storage — fp8 storage alone allows ≈225K. Chunked scoring (lever C3, `4b-chunked-softmax` session) removes it. fp8 + far pool + chunked scoring ≈ 225K would clear the median, ~55% of agent calls. (All derived.)

**3.3 Multi-card does not rescue capacity (derived from measured 175 µs/wafer/token)**
29K → 197K needs ≈6 extra wafers = +1.01 ms/token; decode 1.05 → 2.06 ms, i.e. 954 → 485 tok/s (clock caveat again). Buying capacity by wafer count halves decode.

**3.4 RETRACTED: "171 µs crossing"** — that was the public Cerebras API, not the fabric. Le: card-to-card interconnect is 3–5 µs at 1.2 Tbit/s (150 GB/s); public API does not expose it; the 171 µs is 43× worse than silicon. Rounds 157/158's "the boundary is a wall, AFD dead at bs=1" withdrawn.
Survives: **KV cannot cross a link.** Per token attention reads the whole KV:

| context | KV | over 150 GB/s link | H100 from own HBM |
|--:|--:|--:|--:|
| 29K | 4.01 GB | 26.7 ms/token | 1.20 ms |
| 197K | 27.1 GB | 180 ms/token | 8.08 ms |

Fitting 29K KV into half a 1.0 ms token budget needs ≈8 TB/s — link is 53× short; H100 reads the same KV 22× faster from HBM. Bandwidth-class fact: KV must live with the attention compute (= why NVIDIA AFD keeps attention+KV together).
What the link does buy: activations — 5 KB/layer, 34 ns wire; 36 layers × 6–10 µs round trip = 0.22–0.36 ms/token. So AFD is viable on the real interconnect, but it removes FFN weight traffic, worth 57.3% at 4K but only 15.0% at 197K. AFD is a weights-side solution; dense 4B on an 80 GB GPU is its worst case.

**3.5 Industry context (public sources, fetched)**
- NVIDIA Groq 3 LPX (NVIDIA blog): 500 MB compiler-managed SRAM/chip, 128 GB rack-wide, 150 TB/s on-chip, 96 C2C links = 2.5 TB/s/chip, plesiosynchronous protocol, Attention–FFN Disaggregation (LPX does FFN/MoE; GPUs hold prefill+decode attention and the whole KV), compile-time static allocation, plus 256 GB + 128 GB DRAM.
- Shared design constant: full SRAM sweep ~3.3 µs on LPX, ~2.1 µs on WSE-3. Difference is the boundary: LPX made the chip edge part of the compiler schedule; Cerebras has no edge inside a wafer.
- Cerebras CS-6 adds 3D-stacked DRAM (Hot Chips 2026 post) — the gap named ("SRAM holds the working set, DRAM holds the parameter store; CS-3 has no DRAM tier"). No capacity/bandwidth numbers published; roadmap not shipping. If KV moved there, thresholds: 4.0 TB/s at 29K, 27.1 TB/s at 197K (8.1× HBM), 84.6 TB/s at p90 (derived).

**3.6 SCOPING CAVEAT for the whole summary** — Cerebras quotes CS-5 at "up to 10,000 output tok/s per user" for 31B–120B models (0.10 ms/token) vs our measured 4B dense ~1,000 tok/s (1.00 ms): a model 8–30× larger running 10× faster.
> This session's performance conclusions — including "87% of per-layer time is fixed coordination cost" — are properties of **this kernel**, not the architecture. Label them that way.
Diagnosis corroborated: back-solving Cerebras's rates gives 0.24%–1.52% of aggregate bandwidth → their stack is also latency/fixed-cost-bound. The lever derived (speculative decoding — amortises fixed term and KV scan, where batching amortises only the first; our batching measured 2.2×) is what a production stack uses. "Found the right lever, have not pulled it."
Unaffected: everything trace-based — three workload shapes, AFD's weights-side nature, MoE sparsity inverting sign, KV not crossing a link.

**3.7 Why the hardware advantage does not come out (kernel-scoped; least-squares on measured height ladder)**
T = 10,398 + 855 × W (W = per-PE work). At today's geometry 87% of per-layer time is independent of per-PE work — halving the area moved time 1.4%. Per PE per layer: 3,080 bytes in ~17,688 cycles = 0.174 B/cycle vs ~27 available, 0.63% utilisation. Mechanism: 10 hidden + 16 attn values per PE → QKV matvec is 160 MACs against ~100 cycles of DSD issue setup; 8–9.6K of the fixed term is collectives. "Spread a small model too thin; coordination costs ~2 orders of magnitude more than computation." Aggregate: 6,269× the bandwidth converted into 4.7×; 0.045% utilisation vs H100 59.7%.

**3.8 Positioning recommendation (Rounds 163–164)** — NOT "on-chip SRAM capacity → performance" (loses numerically 167K < 197K, in scope, and directionally: CS-6 and LPX both add DRAM; field moving from total residency to tiering). INSTEAD: **residency** — where is the residency frontier and what does crossing it cost. Three layers:
1. Taxonomy — dense weights tierable; MoE experts must be tiered; KV not tierable (53×); activations trivially tierable. This table is AFD.
2. Placement (novel measured part) — inside the resident tier, per-PE distribution binds, not aggregate capacity: halving width doubles per-PE KV and halves the ceiling; fusion halves it and doubles the ceiling at identical totals. Per-PE footprint not weight-dominated (24.8 of ATTN block's 31.8 KB is code/buffers/KV machinery).
3. Method — across ~12 contested claims this week, the single predictor of survival was whether the measurement carried a control; the failure mode (instrument's property read as the world's) recurred twelve times.
CS-3 is the right platform for this: extremal no-tier point, every residency decision forced into the open.

**3.9 Next, and what is missing** — the frontier is two-dimensional; only depth pushed. Same capacity on depth vs breadth:

| capacity | depth: one request | Mooncake p50 6.9K | ServeGen R1 p50 208 |
|---|---|--:|--:|
| today 29K | 14.7% of agentic median | 4 prefixes | 139 |
| far pool 167K | 84.8% — still short | 24 | 803 |

Recommended order: (1) prefix reuse / breadth — startable in today's 29K; prefill is 7× slower so avoiding a re-prefill is worth 7× more (10.9K tokens: H100 156 ms, CS-3 1,147 ms); ServeGen is 3.9:1 prefill-to-decode by token. (2) near-pool harvesting as mechanism — the one rung already priced (1.17 cyc/word, inside the ≤2 gate, fused-block thread's simfab microbench, which also corrected a 13 cyc/word relay artefact). (3) depth-vs-breadth allocation curve. (4) do not chase 167K/225K as a target.
Two measurements missing: the width axis (four measured points on height, none on width) and the wafer-edge round-trip to a GPU (waits on Cerebras opening the API).

Slide handling notes: (a) resolve the clock before any tok/s appears; (b) every ladder rung (17.6K/26K/95K/167K/225K) is analytical → dashes or "derived" tags; (c) the 87% / 0.63% / 0.045% figures must carry the "this kernel, not the architecture" caveat on the same slide; (d) the 171 µs retraction belongs in a Corrections section like last week's deck; (e) positioning (3.8) is a recommendation from the session, not a decision by Le — do not mark it recommended in a `compare` unless Le says so.

### 3b. Prefix × decode trade-off, four configurations × eleven scenarios  (source: session `4b-wide-layer`, follow-up message 2026-09-14; Round 171 of the wide-layer session report, verified at line 9930. **Supersedes the partial depth/breadth table in 3.9.** Everything derived from measured rates; no new job.)

**Modelling choices (keep attached):** four configurations — CS-3 alone; PD-split (GPU prefill → link → CS-3 decode); H100 alone; GPU-streamed (KV stays on GPU, whole cache crosses per token). Decode rates follow each machine's measured context slope: CS-3 = (681K + 16.1·C) cycles **at 750 MHz** (clock caveat as in 3.1); H100 = 4.60 + 0.0489·C/1K ms (linear fit to measured 1K–32K). H100 prefill uses its measured curve held at the 32K rate beyond 32K — optimistic for H100. Link = 0.98 µs per prefix token (Le's 1.2 Tbit/s; not measured here; API not open). PD-split's decode side is the wafer, so it keeps the 29K ceiling. Per-request wall time, ms.

| scenario | prefix | decode | KV GB | CS-3 alone | PD-split | H100 alone | GPU-streamed | best | decode share |
|---|--:|--:|--:|--:|--:|--:|--:|---|--:|
| Qwen-Turbo p50 (short/tiny) | 680 | 11 | 0.10 | 82 | **21** | 61 | 28 | PD | 48% |
| ServeGen R1 p50 (short/long) | 208 | 792 | 0.03 | 745 | **726** | 3,654 | 888 | PD | 100% |
| long reasoning (short/very long) | 208 | 10,000 | 0.03 | 9,147 | **9,128** | 46,105 | 11,172 | PD | 100% |
| R1 p90 | 2,100 | 3,400 | 0.31 | 3,462 | **3,273** | 16,020 | 10,290 | PD | 99% |
| Qwen-Max p90 (mid/short) | 2,400 | 433 | 0.35 | 668 | **453** | 2,078 | 1,472 | PD | 92% |
| Mooncake conv p50 | 6,900 | 350 | 1.02 | 1,096 | **482** | 1,834 | 2,850 | PD | 77% |
| Mooncake toolagent p90 | 17,000 | 507 | 2.51 | 2,435 | **1,012** | 3,103 | 9,468 | PD | 64% |
| long-doc classification (long/tiny) | 27,000 | 20 | 3.98 | 2,872 | **734** | 796 | 1,238 | PD | 4% |
| Mooncake conv p90 (long/short) | 27,000 | 597 | 3.98 | 3,730 | **1,592** | 4,212 | 17,411 | PD | 56% |
| Mooncake conv p99 | 85,000 | 1,100 | 12.5 | no fit | no fit | **12,075** | 97,363 | H100 | 80% |
| Claude Code median | 197,000 | 5,800 | 29.1 | no fit | no fit | **88,215** | 1,158,677 | H100 | 94% |

**Reading (as given):**
- Prefix length sets PD-split's margin over CS-3 alone (it is the prefill fix): 1.03× at 208 tokens, 1.5× at 2.4K, 2.3× at 6.9K, 2.4× at 17K, 3.9× at 27K.
- Decode share sets PD-split's margin over H100 alone (the decode advantage): 5.0× where decode ≈ 100%, 4.6× Qwen-Max, 3.8× Mooncake p50, 2.6× Mooncake p90, 1.08× at long-doc classification (decode 4%).
- The 29K wall decides participation: above it only H100 serves; PD-split does not extend it.

**Three things to carry (as given):**
1. PD-split wins every scenario that fits; weakest win is long-prefix/tiny-decode where H100 is within 8%. It uses each machine where measured to lead (GPU prefill 7×, CS-3 decode 4.7×). It was ruled out earlier in the report on a 3.2 GB/s H2D measurement; the real link is 62–176× that requirement (Round 169).
2. GPU-streamed column kills "keep KV on the GPU" at every scale: worse than H100 alone in every row except the 680-token one; 8–13× worse above 29K. KV must live with attention compute.
3. Four corners: short-prefix/long-decode (reasoning) = wafer home turf, 5× over H100 alone, PD-split barely needed; long-prefix/short-decode (RAG, summarisation) needs PD-split and H100 is competitive; long-prefix/tiny-decode (classification) nearly a wash; beyond 29K not ours with or without a GPU.

**Caveats (as given):** link figures are Le's, unmeasured here; CS-3 rates are this kernel's, not the architecture's (Round 162 scoping); H100 prefill beyond 32K held optimistic, so the two H100-only rows understate its time; per Round 168 the Claude Code row is a frontier-model workload a 4B never serves — in the table for completeness, not as a target.

**Gap noticed:** Rounds 166–170 exist in the report (9575–9929) and were only referenced, not relayed: R166/167 "advantage is weight residency, not KV residency; a fixed system prompt *is* weights" (Le's correction); R168 "a 4B cannot serve the Claude Code trace's model — applying Round 35's caveat changes the verdict"; R169 PD-split revived; R170 SRAM as absorption buffer with a GPU present, integrated GPU+wafer product. **Ask Le whether any of these goes on a slide**; R167/R168 look like corrections to earlier framing and may belong in the Corrections section.

Slide handling notes: 11 rows exceeds the table cap (7, effectively 5 with title+subtitle) → split by regime (fits / does not fit) or show as a figure; CS-3 columns depend on the 750 MHz choice; "best" column is fine as a coloured pill only if the builder supports custom words — otherwise plain text.

## Candidate slide outline (v1, 2026-09-14, for Le's review)

Convention: every table and every figure on its own slide. T = talk, B = backup/appendix. Numbers on slides come only from entries 1–3b above; "derived" stays labelled.

### Opening
1. T title — "Both sides measured: where the wafer wins, and what it cannot hold" (period 09-07 → 09-13)
2. T statement — three verdicts in one line each: (a) single-stream decode leads 4–5× and grows with context; (b) the workload that wants it does not fit, and no rung of the ladder reaches it; (c) layout C is closed — the kernel is coordination-bound, not FLOP-bound.

### A. The workload (entry 2)
3. T figure — trace_length_distributions.png (subtitle text moved to caption)
4. T bullets — three worlds: Claude Code huge-in/medium-out; Mooncake small-in/small-out; ServeGen R1 small-in/large-out. Only the agentic harness produces "not even one fits". 29K measured / 103K derived.
5. T table — Claude Code main thread vs subagents, shape rows (context p10–p99, first-call context, output p10–max, ≤5-token share) — 4 rows
6. T bullets — subagents are a different shape, not a smaller copy; decode budget lives on the main thread; the 309K in last week's deck was main-thread only, all-calls median is 197K.

### B. The GPU baseline (entry 3.1)
7. T table — CS-3 vs H100, six rows (clock TBD by Le)
8. T bullets — confirmed: prefill 7× behind (finding 10 now measured); killed: the recompute-engine wedge; the sharpest sentence: the advantage applies exclusively to the workload we cannot hold (6.9 s vs 28 s at short context; at 197K H100 ~75 s, CS-3 no fit).

### C. Capacity does not survive the traces (entries 3.2–3.4)
9. T table — ladder rung vs trace percentiles: fusion ~17.6K / split ~26K / near pool 95K / far pool 167K / fp8+chunked ≈225K (all derived) against Claude Code p50 197K, Mooncake p99 62–85K, ServeGen p99 ≤23K — 5 rows
10. T statement — "Capacity cannot reach the workload that wants it; the workloads it reaches do not need it." + reopener (score-buffer wall, chunked scoring, ≈225K clears the median for ~55% of calls).
11. T bullets — multi-card does not rescue: +≈6 wafers = +1.01 ms/token, decode halves (derived from measured 175 µs/wafer/token).
12. T table — KV over the 150 GB/s link vs H100 HBM, 2 rows (29K, 197K)
13. T bullets — KV must live with the attention compute (53× short, bandwidth-class fact); what the link does buy: activations, 0.22–0.36 ms/token; AFD viable but weights-side (57.3% at 4K → 15.0% at 197K).

### D. The prefix × decode spectrum (entry 3b)
14. T table — scenarios that fit, part 1: Qwen-Turbo p50, R1 p50, long reasoning, R1 p90, Qwen-Max p90 — 5 rows
15. T table — scenarios that fit, part 2: Mooncake conv p50, toolagent p90, long-doc classification, Mooncake conv p90 — 4 rows
16. T table — scenarios above the wall: Mooncake conv p99, Claude Code median — 2 rows (Claude Code row flagged "not a 4B target", R168)
17. T bullets — how to read: prefix length sets the margin over CS-3 alone (1.03× → 3.9×); decode share sets the margin over H100 alone (5.0× → 1.08×); the 29K wall decides participation. PD-split wins every scenario that fits. GPU-streamed kills "keep KV on the GPU".
18. T table — depth vs breadth: today 29K / far pool 167K × one agentic request / Mooncake p50 / ServeGen R1 p50 — 2 rows
19. T bullets — recommended order: prefix reuse first (re-prefill worth 7× more to us; ServeGen 3.9:1 prefill:decode), near-pool harvesting as mechanism (1.17 cyc/word priced), allocation curve, do not chase 167K/225K.

### E. Layout C: implemented, measured, closed (entry 1)
20. T figure — 2026-09-13-layoutC-color-regions.png (analytical placement, 8 groups, 650×1028)
21. T figure — 2026-09-10-layoutC-tall-a2.png (one group: A1/A3 left half, A2 right half; 128×80 / 128×160 / 128×256)
22. T table — measured single-layer latency, 2 rows (1,280 / 5,120 KV): 26,377 → 102,511 (3.886×), 28,000 → 104,330 (3.726×); boundary and "not pipelined, not full-model" in subtitle
23. T figure — 2026-09-13-attn-vs-ffn-three-axes.png (re-export or crop needed: subtitle collides with 1200 tick, footnote clipped)
24. T bullets — why: FLOP says FFN 2×, TIME says ATTN 2.05× (measured); the kernel is comm/latency-bound; the MAC model that predicted A3 as pacing stage is withdrawn; ATTN/FFN as independent pipelined stages measured 1.47× at 2K / 1.40× at 8K.
25. T bullets — what stands regardless: first five-layer group with on-wafer feedback runs on CS-3 (10,560 / 5,120 elements exact; 83.9M-value cache probe passes; negative control fails); router-only strip transport validated; two device defects fixed 09-10.
26. T bullets — decision (Le, 09-13): two-group D17 link paused; next = fused 256×256 single block, FFN+QKV on every PE, attention heavy state on 1-in-N PEs; gate = compile-only SRAM of three PE images; first-order ~1.0× original latency in half the area.

### F. Why the hardware advantage does not come out — kernel-scoped (entries 3.6, 3.7)
27. T bullets — T = 10,398 + 855·W: 87% of per-layer time independent of per-PE work; 0.63% per-PE bandwidth utilisation; 160 MACs against ~100 cycles of DSD setup; 6,269× bandwidth → 4.7×. **Same slide carries the caveat:** CS-5 quoted at 10,000 tok/s on 31B–120B; these are properties of this kernel, not the architecture. Diagnosis corroborated (their stack also <2% of bandwidth); lever = speculative decoding, not yet pulled.

### G. Industry context and positioning (entries 3.5, 3.8)
28. T bullets — LPX (500 MB SRAM/chip, 2.5 TB/s C2C, AFD with GPUs holding attention+KV, compile-time static allocation, +DRAM) and CS-6 (3D-stacked DRAM, roadmap, no numbers); shared constant: full SRAM sweep 3.3 µs vs 2.1 µs; the difference is the boundary.
29. T compare — "capacity → performance" vs "residency frontier" — **both unmarked** (session recommendation, not Le's decision); residency's three layers (taxonomy = AFD; placement: per-PE distribution binds; method: controls predicted survival across ~12 claims).

### H. Decide
30. T next_steps — open decisions for the meeting: (1) clock convention for every tok/s (750 MHz vs 0.85 GHz); (2) fused-block gate go/no-go criteria; (3) prefix-reuse/breadth as the next workstream; (4) the two missing measurements (width axis; wafer-edge round trip, waits on Cerebras API); (5) whether to adopt the residency framing.

### Corrections (section divider + one slide each)
31. section — Corrections
32. B bullets — per-PE MAC breakdown withdrawn (figure per-pe-work-model.png retired); 2.65× floor and 0.31×/0.62× throughput went with it.
33. B bullets — 171 µs crossing was the public API, not the fabric: 3–5 µs at 1.2 Tbit/s per Le; "boundary is a wall / AFD dead" withdrawn; KV-cannot-cross survives.
34. B bullets — last week's "median context 309K" was main-thread only; all-calls median 197K.
35. B (pending Le) — R167 "a fixed system prompt is weights" and R168 "a 4B never serves the Claude Code model" if Le wants them presented.

### Appendix (B)
36. section — Appendix
37. B table — per-request length distributions, Claude Code + Mooncake (6 rows → 5+1 needs split: 3 CC rows / 3 Mooncake rows → two slides 37a/37b)
38. B table — per-request length distributions, ServeGen four models (4 rows)
39. B table — main thread vs subagents, behaviour rows (output share, intra-turn gap, calls per session, output p50 by model) — 4 rows
40. B table — three-axes numbers as a table (MACs / cycles / KB for ATTN and FFN) — 2 rows
41. B figures — 2026-09-10-layoutC-hidden-reshard.png; 2026-09-10-layoutC-weight-axes.png (one slide each)
42. B figure — 2026-09-13-layoutC-single-layer-performance.png
43. B table — layout C geometry (A1/spare/A3/A2 cols×rows, rows/PE, PE counts) — 4 rows
44. B table — CS-6 DRAM thresholds if KV moved there (4.0 / 27.1 / 84.6 TB/s) — 3 rows, derived
45. B table — LPX spec sheet (public) — ≤5 rows

Not in deck: the Round 171 modelling-choices text goes to speaker notes of 14–16; supporting measured numbers in entry 2 (decode cycle model, 99% successor re-read, 13.9 s reload) are last week's material — cite in notes only.

## Facts pulled from the repo to fill gaps (to list in reply, per wafer-slides rules)

(none yet)
