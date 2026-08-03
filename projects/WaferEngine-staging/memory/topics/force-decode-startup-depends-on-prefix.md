---
summary: Force-decode startup depends on prefix length — 2026-08-02
tags: [WaferEngine-staging, drained-inbox, 2026-08-02]
---

# Force-decode startup depends on prefix length — 2026-08-02

This topic was created by the 2026-08-03 maintain pass from a dated inbox capture. Keep it as the durable, topic-scoped home for the finding; the original capture is marked drained.

## Drained capture — 2026-08-02

Source: `memory/inbox/2026-08-02-force-decode-startup-depends-on-prefix.md`

# Force-decode startup depends on prefix length — 2026-08-02

**Project:** WaferEngine-staging
**Author:** codex
**Status:** captured

## What happened / finding

- Situation: when extending E9/E10D's force-decode cost model beyond its fixed 256-token
  starting prefix, subtracting the `F=1` span as a universal approximately 22 ms pipeline
  offset produces misleading marginal costs at long prefixes.
- E14 measured real WSE-3, Qwen3-1.7B, 2x4 blocks, TSC at 0.85 GHz, commit `6ecb496`,
  over `P={256,1024,4096,8192}` x `F={1,256,512,1024,2048,4096}` (24 rounds,
  device verdict PASS, n=1). `F=1` spans were 22.037, 26.426, 110.389, and
  224.211 ms respectively. The old approximately 22 ms offset is only a `P=256` fact.
- The anomaly is localized to the startup transition `F=1 -> 256`. After excluding that
  transition, 16 adjacent-F marginal segments across all four prefixes collapse onto
  `f_forced(position) = 71.745198 us + 4.093307 ns * position`, `R^2=0.997447`,
  RMSE 0.681 us/token. Thus steady forced cost is position-only; startup needs a separate
  prefix-dependent anchor `D(P,256)`.
- Correct two-piece model for `F>=256`:
  `D(P,F)=D(P,256)+sum_{q=P+256}^{P+F-1}(71.745198 us + 4.093307 ns*q)`.
- A matched-final-context boundary with `L_new=256` is not one scalar. Model-derived
  delta-reload crossings `D(S,H+L_new) = I(H)+D(S+H,L_new)` are H*=744, 1079,
  and 864 at S=256, 1024, and 4096. Full-context reload `I(S+H)` moves them to
  932, 2756, and no crossing through H=4096. Therefore the old approximately 700-token
  result is the S=256/delta-reload slice of `H*(S,reload_policy,L_new)`.
- Two n=2 attempts ended in EPCC ingress 502. One repeat wafer job itself succeeded but
  its evidence bundle did not reach the launcher, so it was correctly not counted.

## Implications / next actions

- [ ] Replace universal `F=1` offset subtraction in the M2 model with a measured
      prefix-dependent startup anchor; use segment differences beginning at F>=256 for
      the steady curve.
- [ ] Sweep `F={1,16,32,64,128,256}` by prefix to resolve the startup transition.
- [ ] Run matched-context direct witnesses at `S=1024,H={1024,1280}` and
      `S=4096,H={768,1024}`, `L_new=256`, after ingress stabilizes.
- [ ] Obtain n=2; do not count a succeeded wafer job without a downloaded, hash-verified
      evidence bundle.

## Pointers

- ContextBase tracking doc: `https://context.ed-aisys.com/doc/m2-experiment-register-index-results-three-lane-design-X3DIdKV2s4` (E14 row + full Chapter 2 result, verified 2026-08-02)
- Agent-memory experiment register: `memory/topics/m2-experiment-register.md` (E14 row + full result)
- `/home/lexu/we-m2-prefix-fd-sweep/models/qwen3_1p7b-e2e-pdSeparate/request_config/e14_prefix_fd_sweep/E14_RESULTS.md`
- `/home/lexu/we-m2-prefix-fd-sweep/models/qwen3_1p7b-e2e-pdSeparate/request_config/e14_prefix_fd_sweep/e14_grid/e14_model.json`
- `/home/lexu/we-m2-prefix-fd-sweep/models/qwen3_1p7b-e2e-pdSeparate/request_config/e14_prefix_fd_sweep/e14_grid/e14_boundaries.json`
- Related capture: `memory/inbox/2026-07-31-forced-token-cost-is-a-curve-not-a-constant.md`
