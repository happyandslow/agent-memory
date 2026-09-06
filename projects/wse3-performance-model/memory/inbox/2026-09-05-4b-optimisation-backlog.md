# Qwen3-4B decode/forced-prefill optimisation backlog (every lever found in session 4b-wide-layer, with its measured basis) — 2026-09-05

**Project:** wse3-performance-model
**Author:** claude (session 4b-wide-layer)
**Status:** captured — Le asked to record all optimisation points for a later joint revisit

Canonical table with basis/effect/status per lever: report §2c,
`docs/reports/2026-09-04-4b-wide-layer-session-report.md`
(https://claude.ai/code/artifact/52cee6ad-bc9a-4883-bcbc-dfd2b98fe338).
Summary:

- **A. Inside a layer (stage period):** fewer/longer DSD ops (softmax
  prologue is per-slot overhead, ~960 cyc/layer at bsz 1, 37 % of the phase
  at bsz 8); cheaper exp kernel (the only context-scaling pass, 69 % of the
  context slope); fixed collectives (~2K cyc/layer in softmax, 6–8 Y
  all-reduces/layer; score band all-reduce grows with context); P·V
  position-inner and fewer score passes (3–10× on the slope at current
  layout); whole-head layout + flash-decoding merge (~10–15×, removes score
  wall); SiLU back in D-cache (~1 %). **Rejected:** exact softmax fusion
  (−8…−14 % on the phase, measured).
- **B. Pipeline (tokens in flight):** 4 → 8 stages measured 1.47×;
  production forced tail removes 35.8K/120K cyc/token at thin stages;
  finer cuts (3 or 5 stages/layer) 1.3–1.8× derived, equal-area testbed in
  progress; thin layouts B/C/D 31–43K tok/s under flat-time assumption;
  asymmetric pairing (FFN layers per block = round(T_attn/T_ffn), cap 3);
  FFN at bsz b for one request; intra-batch causal attention up to 1.6×;
  two wafers (capacity 53–58K or 2× stages).
- **C. Capacity:** text-slim done (29,184 device ceiling); ingress tile
  streaming (7.1 KB at 29K on 64×128) and chunked scores (5.3 KB) make
  layout C hold 29K; fp8 KV 51K; near/far pools 95K/167K (price
  unmeasured); ~8 KB boot-only code pageable.
- **D. Model/algorithm:** speculative decoding / MTP (up to k× on slope and
  fixed term — most general for a latency-bound kernel); sliding-window /
  hybrid models (5–10× context per wafer); KV eviction / sparse selection.

Measured anchors: Rounds 26, 37, 39, 44, 45, 48, 49.
