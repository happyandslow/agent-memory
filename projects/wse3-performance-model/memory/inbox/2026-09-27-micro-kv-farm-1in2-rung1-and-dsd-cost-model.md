# 1-in-2 micro KV farm rung 1 on CS-3: streaming is free, doubled per-PE positions are not; the DSD "long axis" cost rule — 2026-09-27

**Project:** wse3-performance-model
**Author:** claude (session 4b-multicore-prefetch)
**Status:** captured

## Situation this applies to

You want more decode context per request on the shipped Qwen3-4B decode block
(4 rows × [ATTN 256² | FFN 256²]) by turning each ATTN PE into a vertical pair
(even row = compute, odd row = K/V storage that streams north every layer), or
you are pricing any design that moves KV off the PE that scores it, or you are
about to estimate the cycle cost of a CSL loop from its pseudocode.

## What was built and measured (all on CS-3, 2026-09-27)

Tree: `demo/micro-kv-farm/` (branch `micro-kv-farm-1in2`, uncommitted;
`code/baseline/` = shipped `93a6d0e`, `code/pair/` = variant, docs
`CHANGE-MAP-zh.md`, `ROUTING-PROFILE.md`, `code/pair/IMPLEMENTATION-NOTES.md` §6).
Rung 1 = policy A (today's ownership rule), option N (storage rows join the two
softmax Y-reduces with −inf / 0), stage 1 (bulk K then V per layer into small
compute-row buffers, async receive + sentinel poll).

| context | shipped cyc/token | pair cyc/token | delta |
| --- | --- | --- | --- |
| 512 | 672,702 / 672,115 / 672,109 | 749,487 / 750,051 / 749,474 | +11.4 %, +2.1K/layer |
| 7,936 | 812,318 | 1,035,962 | +27.5 %, +6.2K/layer |

Correctness: all runs `[run] SUCCESS`; at 512 the full 64-token sampled
sequence and the sha256 of the (64,1,20) top-20 index tensor are identical
shipped vs pair. Device msize at 8K: shipped ATTN 39,248 B/PE (no route-table
lever; the farm session's 34,096 had it, −5.2 KB), pair compute row 44,896 B;
`cs-readelf -m` cannot separate the storage variant (reports the region figure).

**Reading:** slope 512→8K is 134 cyc per PE-position per layer shipped vs 274
for the pair, whose compute row holds 2× positions. A streamed remote position
costs the same as a local one — **moving K/V into the FMA is not the cost**.
The pair pays (a) ~2.1K/layer fixed (issue/poll/storage sync) and (b) doubled
per-PE position work at the shipped per-position rate, with no shorter
Y-reduce to offset it. The height ladder's "128 rows −1.4 %" was at 2K context
(8→16 positions/PE); it does not predict 8K.

Policy A adds no capacity by construction (compute row keeps its own cache and
gains score arrays + buffers). Capacity needs policy B (fill compute first,
then storage; role-dependent ingress tiles).

## Decisions (Le, 2026-09-27)

- **Option P** (storage rows as router pass-through for the two softmax
  Y-reduces; fourth route mode "axis 4", virtual row index, re-parametrised
  collectives, storage rows tap the O broadcast) is the next clear optimisation
  inside this design.
- **P·V rewrite** (lever A4/A5 of the 4b-wide-layer backlog: V stored dim-outer
  `Vt[c][p]`, one long op per (head, dim) instead of one length-4 op per
  position) is a profile-gated, design-independent optimisation: do it in its
  own demo and merge as a separable feature; first measure the DSD fixed cost
  on device.

## The DSD instruction cost model (procedural — candidate for a skill)

A DSD op costs ≈ F + L·c: F = fixed issue (DSR loads, address setup, pipeline
fill/drain), c ≈ 1 cyc/element (device-measured 1.0–1.18 in the streaming and
chain microbenches), L = op length. **Both loop orders are O(n); the choice
decides whether F sits inside the per-position slope (paid n× per head) or is
amortised (paid once per output).** Rule: run the DSD along the data's long
axis. For the block layout (kv_cols C = 4, G = 4 heads): current P·V slope
G·(F+C) per position vs target 2·G·C = 32 with fixed 2·G·C·F; target wins iff
C < F. For a farm PE (C = 128) the position-inner form is already right. F ≈ 30
is a FIT to the measured 134 slope, not a measurement (the 134 also holds the
16 score passes, exp, band all-reduce) — measure F and c with a 20-minute
device microbench (`@fmachs` at L = 4/8/32/128) before deciding.

## Pointers

- `demo/micro-kv-farm/code/pair/logs/cs3/round{1,2,3}/` (wsjobs
  9dcsvbvestinkua4fbar2p, eu5weyqrtxyrmpx8kxcqqj, prvtpdjbihbo344c7xuquu,
  jen4mltpe7boftluqovukx, plus reruns).
- Backlog A4/A5: `docs/reports/2026-09-04-4b-wide-layer-session-report.md`
  lines ~10278-10279 and Round 17.
- Claude auto-memory: `micro-kv-farm-rung1-state`, `micro-kv-farm-1in2-direction`.
