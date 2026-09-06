# Qwen3-4B block times vs batch (ATTN/FFN never invert) and the thin-stage SRAM fit — 2026-09-04

**Project:** wse3-performance-model
**Author:** claude (session 4b-wide-layer; sweep by subagent 4b-block-tsc)
**Status:** captured

## Situation

You are sizing pipeline stages for the 4B decode kernel (forced prefill /
"decoder as prefiller"), pairing ATTN and FFN blocks unequally, or asking
whether a one-layer-per-block layout fits in 48 KB per PE.

## Finding (measured, CS-3, row-0 block TSC, 2K context, bsz 1/2/4/8; tokens byte-identical to unprobed runs; jobs wsjob-vbup5y3tqg7dfsfveohc67, -2ppwceqpbmzgepdktor4qn, -ukw6zeykrbvgrkyyl9s2qb, -suwlgvelxzgzpuzfk2sgzq, -rjndmtb9uashxf3tc7stvs)

| bsz | T_attn (row, 9 L) | T_ffn | ratio | row period | rows-as-stages tok/s | ATTN/FFN-split tok/s |
| --: | --: | --: | --: | --: | --: | --: |
| 1 | 106,645 | 51,964 | 2.05 | 690,512 | 4,729 | 7,033 |
| 2 | 168,577 | 77,056 | 2.19 | 1,077,654 | 6,107 | 8,898 |
| 4 | 292,757 | 127,240 | 2.30 | 1,843,888 | 7,143 | 10,247 |
| 8 | 538,793 | 226,604 | 2.38 | 3,383,166 | 7,839 | 11,136 |

- Fits: T_attn = 45.2K + 61.7K·b, T_ffn = 27.2K + 24.9K·b cycles per row.
  Context adds 3.3 cycles per context token per batch element to ATTN only
  (bsz 2: 168.6K @2K → 209.3K @8K; FFN flat). Row occupancy 23 % at every b.
- **The ATTN/FFN ratio never inverts** — FFN's 2.85× MACs do not show; both
  blocks are issue-bound; ATTN grows faster with batch (6.9K vs 2.8K cycles
  per layer per element) and is the only one growing with context. ratio ≈
  2.4 (bsz 1, 8K), 2.9 (1, 16K), 3.8 (1, 29K), 3.1 (8, 8K).
- Pairing rule for a shared FFN block: layers per block = round(ratio),
  capped at 3 by SRAM (9.1 KB per FFN layer at 128²).
- With the current 4-row geometry, batching alone gives 7.8K tok/s forced
  prefill at bsz 8 and 11.1K with ATTN/FFN as independent stages — past
  native prefill (9.3–9.8K) before any re-layout.

## Thin-stage SRAM fit (static accounting, `demo/qwen3-4b-thin-stage/sram_fit.py`; rules reproduce today's 29K device ceiling to 1 KB)

- Role blocks 64×128 (8,192 PEs), one layer: ATTN 36 KB @8K, 43.5 KB @16K,
  55 KB @29K → fits to ≈ 18K as-is; the 29K overflow is the KV-ingress
  staging tile (one layer's K cache, 7.1 KB) + score buffers (5.3 KB) = the
  streamed-ingress / chunked-score levers. FFN 64×128 35 KB; shared FFN 128²
  32.7 KB (2 L) / 41.6 KB (3 L).
- Fused one-layer block 128² (both codes + both weight sets) 45 KB @8K —
  tightest; ≈ 10K context unless code shrinks.
- Generator hard-caps the 4B at 4 rows today: P ≥ 256 because the HT-head
  embedding tile is 2·vocab·dim/P² (76–95 KB at P = 128); thin stages need
  the HT band decoupled from P, a multi-lane serpentine, 1–2 layers/block.

## Pointers

- `analyses/2026-09-04-4b-block-tsc-bsz/` (README, results/block_tsc_bsz.json)
- `demo/qwen3-4b-thin-stage/README.md`, figure `assets/2026-09-04-4b-thin-stage-layouts.png`
- Report Rounds 20–26: `docs/reports/2026-09-04-4b-wide-layer-session-report.md`
- Related: `2026-09-04-4b-row-is-serial-attn-ffn-block-times.md`, `2026-09-04-4b-decode-cost-vs-context-and-device-ceiling.md`

## Step 1 measured (2026-09-05, subagent 4b-thin-stage-forced) — forced prefill on the 4-row geometry

Forced mode = runtime flag + token list baked on the HT head; tail skips only
its sampled-token emit; same image both modes. Measured 750 MHz: **5,006 tok/s
at 2K context (149,811 cyc/tok), 4,507 at 8K (166,407)** vs serial decode
1,115 / 954 → 4.5–4.7×. Rows-as-stages prediction over the same TSC window
4,795 / 4,369 → measured/predicted 1.044 / 1.032; the surplus is the one legal
cross-token overlap (ATTN starts t+1 layer 0 while FFN finishes t layer 8,
≈ 5.6K cyc); refined ratio 1.007 / 0.998. **No pipelining penalty at 4
stages — the 1.7B 0.82 bubble factor does not apply to the 4B.** Gates:
byte-identical records sim + device, negative control diverges at the
expected step, free TSC reproduces 954.2 @8K. wsjobs d46iukzpnbdb2jp3obmum3,
f4pbfv3uetmpyzcf87gi2y, 9t9d8hgzjxhdnt2vzzufrx, 9sdgqjhg5nin2udesnjrcz.
Files: `demo/qwen3-4b-thin-stage/step1-*`, `results/step1_results.json`.
Gotcha: the head PE is 89 % full with a 16.4 KB baked token list at 8K — a
production feed must stream tokens.

## Compiled SRAM supersedes the fit tables; i8 KV-stride floor (2026-09-05, Le's rule: compiled numbers only)

Real-geometry compile-only builds of the one-layer cut (i) strips at 2K:
**height 16 does not compile** — the KV-cache DSD stride is an 8-bit field,
so `kv_len_per_pe` ≤ 127 positions per PE → KV-holding stages need ≥ 32
rows at 2K and ≥ 128 rows at 8K (widening to i16 = separate surgery).
**Height 32 compiles**: per PE ATTN 32.2 KB, FFN 27.8, strips 4.0, head
27.3, tail 42.8 (cs-readelf). Also: the FFN inner dimension is
width-sharded, so FFN activation buffers do NOT grow at thin heights — both
hand-derived fit tables (Rounds 33/52/53) mis-scaled them. Rule from Le:
never hand-derive per-PE SRAM; every runnable deployment ships its compiled
per-stage, per-PE breakdown next to its wsjob id.
