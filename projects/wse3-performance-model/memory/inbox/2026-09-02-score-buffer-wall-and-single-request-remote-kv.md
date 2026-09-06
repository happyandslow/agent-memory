# Score-buffer wall, single-request remote KV, and pricing SRAM levers — 2026-09-02

**Project:** wse3-performance-model
**Author:** claude
**Status:** captured

## Situation

You are trying to raise the resident KV context of Qwen3-4B decode on WSE-3
by freeing or borrowing SRAM (code slimming, KV fp8, moving K/V off the ATTN
PE, using idle PEs), and you want to know (a) how far each lever gets you,
(b) why the numbers stop adding up past ~100K tokens, and (c) how to compare
levers whose performance cost is paid at different times.

## What happened / finding

- **Score-buffer wall (analytical, from the 2026-09-02 compiled breakdown
  constants).** Per 256-token slot the decode ATTN PE keeps `score` 8 B +
  `score_f32` 16 B + 8 B staging = 32 B that is the *working scratch* of
  softmax on that PE and cannot be parked; K/V (144 B/slot bf16, 72 fp8) is
  persistent state and can. With ≈ 21 KB context budget per ATTN PE that is
  ≈ 650 slots ≈ **167K tokens** even with every K/V byte elsewhere (wafer:
  ATTN budget ≈ 5.47 GB ÷ 32,768 B/token). Invisible in bf16 (K/V fills SRAM
  first); **binding after KV-fp8 and/or K/V relocation**. Le asked for and
  confirmed the plain-language reading: K/V = archive (can go to the
  warehouse), scores = the scratch paper on the desk.
- **Corrected capacity ladder (bsz 1, static link accounting, after the
  route-table `.text` slimming that freed ATTN 10,408→15,426 B, FFN
  14,504→18,998 B):** ATTN-only bf16 = 30,464 (compile-swept by the other
  session; route table A/B'd on CS-3 at 8K, byte-exact, TSC +0.007%);
  + KV fp8 ≈ 51K; + FFN pool
  (per-step fabric stream) ≈ 95K; + far pool (227K unplaced PEs, HT head,
  strips) → clipped at the 167K wall. bf16 alternates: FFN pool ≈ 56K, far
  pool ≈ 120K. An earlier in-session ladder (60K/98K/207K) was an arithmetic
  slip; do not reuse it.
- **Unlock = chunked / online-softmax scoring** (fixed-size chunk, running
  max/denominator/output, rescale on max change). The prefill artifact
  already does chunked attention (`CHUNK_SIZE=1024`, `score_f32` fixed
  2,048 B). Chunked scoring and per-step K/V streaming are one design: the
  streamed chunk is the scored chunk. Price class P2 (per-step), expected
  small; unmeasured.
- **Distinction Le insisted on:** the existing on-chip SRAM-offload line (U2
  witnesses, M4 policy, park/reload) targets *multiple requests'* KV at
  session/turn granularity (price P1). Extending *one request's* active
  context with per-step streaming from non-local SRAM is a different design
  with a different price class (P2). Shared: movement templates,
  queue/color budget, the streaming microbenchmark (viability gate ≤ 2
  cycles/word vs as-built 13–43). Not shared: policy, granularity.
- **Per-token host streaming is dead on arrival:** decode scans the whole KV
  each step (32K context ≈ 4.8 GB/step); host↔wafer IO is single-digit to
  ~12 GB/s. Per-step streaming may only ride the fabric; host IO moves KV at
  turn/session granularity only.
- **Pricing methodology decision (Le):** SRAM levers are compared by a
  *merit order* keyed on when the cost is paid (P0 one-time / P1 per turn /
  P2 per step / P3 accuracy gate), normalized only under a stated workload
  profile; unpriced levers are drawn hatched, never assumed free. A single
  formula was rejected because lever price and value depend on the already
  applied set (the wall example). Cards + generated chart live in the repo
  (pointers below).
- **Geometry is SRAM-neutral to first order:** per-PE weights/KV are ~invariant
  across block shapes at equal total compute PEs (P must divide
  2560/4096/9728 → {128,256,512}); layout choice is a latency/throughput
  question, not a capacity lever.
- **Model-size scaling hits weights, not KV:** Qwen3 family keeps 8 KV heads
  × 128, so KV/token is ~constant (4B/8B 147 KB, 14B 164 KB, 32B 262 KB);
  8B bf16 fits with ~100K-token headroom, 14B is tight, 32B needs fp8
  weights or streaming. KV-capacity machinery transfers across sizes.

## G(C) trace study, first pass (measured on local Claude Code transcripts, Claude tokens)

- 1,045 contexts / 102K API calls (2026-06-10..09-02): **96 % of input
  tokens are re-sent prefix**; ~19 API calls per user turn; median 1.9K new
  + 441 decode tokens per call against a 284K median context.
- **Harness base context p50 = 51.5K** at the first call of a session
  (subagents 18.5K) — a native-32K Qwen3-4B cannot host the harness as-is;
  the 262K `Qwen3-4B-Instruct-2507` checkpoint (same architecture) or a 3–5×
  smaller harness is a precondition, independent of any kernel work.
- Marginal demand `dG/dC = P(ctx > C)`: 0.93 @32K, 0.80 @64K, 0.59 @131K,
  **0.51 @167K (score wall)**, 0.36 @262K → on this workload demand does not
  cut the supply merit order before the wall; the cut is set by price alone.
  Caveat: 1M-context models with no compaction pressure; one power user.
- Doc: `docs/analysis/2026-09-02-gc-trace-study-first-pass.md`; scripts and
  counts-only traces in `analyses/2026-09-02-gc-trace-study/`.

## Implications / next actions

- [ ] Separate session: design doc for chunked score + single-request stream
  (`docs/session-prompts/2026-09-02-single-request-remote-kv-and-chunked-score.md`).
- [ ] This session: G(C) demand-curve trace study (per-step
  `cache_read/cache_creation/output` usage fields in local Claude Code
  transcripts already give the prefix/suffix/decode decomposition).
- [ ] Re-run `sweep_seqlen.sh` on the slimmed artifact to pin the 30.2K
  extrapolation.

## Pointers

- `docs/design/2026-09-02-sram-performance-exchange-methodology.md`
- `analyses/2026-09-02-sram-perf-exchange/{levers.json,plot_exchange.py,results/sram_perf_exchange.png}`
- `docs/design/2026-09-02-attn-column-split-compute-storage-hypothesis.md` (§4–8, addendum A4)
- `docs/analysis/2026-09-02-qwen3-4b-sram-usage-observation.md`
- related inbox: `2026-09-02-qwen3-4b-per-role-sram-breakdown.md`
