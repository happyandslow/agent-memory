# Force-decode startup depends on prefix length — 2026-08-02

**Project:** WaferEngine-staging
**Author:** codex
**Status:** drained

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

## Implementation audit and physical model

- The measured interval is `T_observed(P,F) = T_ready(P) + T_fill(P) +
  T_steady(P,F) + T_tail(P+F-1)`. In the older three-term shorthand,
  `T_fd = T_steady + T_tail`.
- The HT_tail timer begins after a west-edge result sender emits the `[N,F]` header but
  before the first Z arrives. This is local progress, not an all-PE readiness barrier, so
  `T_ready` can contain residual KV receive/copy, OQ7 flush, ingress-to-broadcast rebind,
  round reset, and cross-PE readiness skew.
- With stage layer counts `[2,4,4,4,4,4,4,2]`, estimate first-token fill as
  `T_fill(P) ~= (28/4) II(P) = 7 II(P)`. Combining this with the free-decode fit gives
  `T_tail(q) ~= f_free(q)-7II(q) = 121.484 us - 0.000338 us*q`, approximately 0.12 ms.
- The resulting F=1-based readiness estimates are 21.406, 25.774, 109.649, and
  223.355 ms for P=256, 1024, 4096, and 8192. Fill is only 0.510-0.737 ms and tail
  approximately 0.12 ms, so the long-prefix growth is overwhelmingly pre-first-token
  readiness rather than transformer pipeline fill.
- Regression method: for each adjacent segment with `F_lo>=256`, compute
  `y=[D(P,F_hi)-D(P,F_lo)]/(F_hi-F_lo)` and assign it mean absolute position
  `x=[(P+F_lo)+(P+F_hi-1)]/2`. Unweighted least squares over 4 prefixes x 4 segments
  gives `II(q)=a+bq`, `a=71.745198 us`, `b=4.093307 ns/position`.
- Therefore `T_steady(P,F)=sum_{j=1}^{F-1}II(P+j) = (F-1)a +
  b[(F-1)P + F(F-1)/2]`. There are F-1 completion intervals because the first token
  is represented by readiness plus fill.
- `D(P,256)` plus the steady curve predicts all measured F=512...4096 points within
  0.90 ms. Exact separation needs a same-PE timestamp immediately after first-Z receive;
  three currently unused words in the 16-u32 TSC burst can carry it.

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
