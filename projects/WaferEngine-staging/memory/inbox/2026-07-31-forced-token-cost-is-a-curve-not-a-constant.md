# Forced-decode token cost is a curve, not the single 13.5% number — 2026-07-31

**Project:** WaferEngine-staging
**Author:** claude
**Status:** drained

## Situation this applies to

You need to price "rebuild this KV by force-decoding it in place" against reloading it,
and you reach for the force-decode cost. The number on record is a **single point**
(S2: forced token = 13.50% of a free one, 88.35 µs, measured at `F = 64`). You are about
to multiply it by an `L` in the thousands.

## Finding — E9, real WSE-3

Forced-token cost **rises with context**, the same way free-token cost does. Measured as
segment marginals so the step-0 pipeline fill cancels:

| segment (F) | µs / forced tok | mean ctx | free µs at that ctx | forced/free |
|---|---|---|---|---|
| 512→1024 | 76.26 | 1,024 | 652.7 | 11.7% |
| 1024→2048 | 79.51 | 1,792 | 674.4 | 11.8% |
| 2048→4096 | 85.54 | 3,328 | 717.9 | 11.9% |
| 4096→8192 | 98.05 | 6,400 | 804.9 | 12.2% |
| 8192→20224 | 134.26 | 14,464 | 1,033.2 | 13.0% |

```
f_forced(pos) = 71.40 µs + 4.317 ns × pos        R² = 0.99932, n = 5
f_free(pos)   = 623.70 µs + 28.315 ns × pos      (S30, n = 22)
   intercept ratio 11.4%   slope ratio 15.2%
```

**The forced/free RATIO is near-constant at 11.7–13.0% across a 40× context range** — and it
brackets both prior estimates (S2's measured 13.50%, the older mock-weight prediction
11.7–12.0%). So the ratio is the durable quantity; the *absolute* 88.35 µs is not.

⇒ Using 88.35 µs flat **understates** force-decode at long context by up to ~1.5× and
overstates it at short context.

## The control did not do what it was designed to do

`F = 1` was the intended "one steady step" control. It returned **22.03 ms** — 34× a decode
step. Reason is structural: the tic is at the top of `tail_step == 0` and the toc at the top of
`tail_step == 1`, and step 0 includes waiting for the first Z through the whole prefill handoff
and 8 blocks. **It is a pipeline-fill measurement, not a one-step control.** An affine fit on
`F ≥ 512` puts the intercept at −71 ms, nowhere near +22 ms, confirming a single constant offset
does not describe the data — which is why the marginals above are the right lens.

**Next time:** a "smallest possible payload" control measures start-up, not unit cost, whenever
the first unit is also the pipeline fill. Use segment marginals from the outset.

## Also validated on hardware

`F == N` (20224) returned `fd_f_device = 20224`, non-zero — the deferred terminator-emit path
(the `tsc_emitted` fix for a review-found bug where `F == N` silently reported nothing) executed
correctly on its first ever hardware run.

## Setting

Qwen3-1.7B real weights, pdSeparate, one CS-3/WSE-3 (EPCC), `serve_2x4_8k20k_e9`
(= `_s2` + `FORCED_MAX` 20224), Pw 512×Ph 1024, 2×4 blocks, `L_p = 256` every round,
7 rounds `F = 1,512,1024,2048,4096,8192,20224`, batch 1, device TSC @ 0.85 GHz, **n = 1**.

## Pointers

- `topics/e9-forced-segment-tsc.md` (instrument design + the two silent-failure bugs)
- evidence on CS-3: `m2bench/evidence/e9_fsweep/{timing.json,results.json}`
- fixture: `request_config/e9_fsweep/` (committed in `942e549`)
