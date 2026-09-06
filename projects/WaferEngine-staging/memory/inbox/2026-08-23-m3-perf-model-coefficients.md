# M3 park/reload as-built performance model — coefficients pinned (Exp-A/C) — 2026-08-23

**Project:** WaferEngine-staging
**Author:** claude
**Status:** drained (2026-08-24 → topics/m3-idle-pe-tier.md)

## Situation this applies to

Estimating M3 round-boundary offload/reload cost for ANY (payload, block
height, storage distance) without re-running hardware; or citing a µs figure
from this line of work and needing the clock convention.

## Clock convention decision

**0.85 GHz (Le, 2026-08-23)** for this path. Device CYCLES are authoritative
everywhere; µs in results/*.json dated ≤2026-08-22 used 1.1 GHz (×1.294 to
re-express). NOTE: `bench/layer_block/utils.py` still carries FREQ_GHZ=1.1 —
a known in-repo convention conflict, flagged not silently unified. Free-token
ratios are computed cycles-to-cycles (decode token anchor 654.95 µs @1.1
= 720,445 cyc), so they survive any clock change.

## Model (as-built; perf_model.py at commit e9e6ec8, selftest 15 anchors ≤0.89%)

    t_full(N, E, D) [cycles] = (c_floor_per_row·N + c_floor_const)   # floor, E=4 basis
                             + (E−4)·N·c_word_roundtrip              # linear payload regime
                             + 2·(D−1)·t_hop_router                  # storage distance

Why this form: the cycle is a PIPELINE — per-word stage costs combine by
max() (slowest stage binds; as-built that is CE per-wavelet work), while
one-time end-to-end latencies (fill/propagation) sum once into the floor.
Validated: park span alone = c_park_storage·N·E within 1% at every N.

## Terms (each pinned by a named experiment; all AS-BUILT)

| term | value | = µs/ns @0.85 GHz | meaning | pinned by |
|---|---|---|---|---|
| n_block_rows (N) | 32..256 | — | compute PEs per column (=P_BLOCK_SIZE) | Exp-A axis |
| words_per_pe (E) | 4·lpb·⌈L/256⌉ | — | per-PE payload in u32 words | payload sweep axis |
| distance (D) | ≥1 | — | rows from block bottom to storage row | Exp-C axis |
| c_park_storage | 43.3 cyc/word | 50.9 ns | park serial consumer = storage CE data task | Exp-A P1 (−0.7% uniform, 4 N values) |
| c_word_roundtrip | 86.3 cyc/word | 101.5 ns | full-cycle marginal per word-per-PE (park+reload) | E sweep + Exp-A P2 (∝N to 0.03%) |
| c_floor_per_row | 245.4 cyc | 288.7 ns | door-open flush chain per row (baton-serialized) | Exp-A P3 (linear fit, resid 8.8 ns) |
| c_floor_const | 326 cyc | 0.38 µs | N-independent floor (GO inject, join, fence land) | Exp-A P3 intercept |
| t_hop_router | 2.0 cyc/hop | 2.35 ns | router transit latency, no CE | Exp-C (+25 ns @D=8, +112 ns @D=32 = exactly 2·(D−1)) |
| bw_link_ref | 3.91 GB/s | — | REFERENCE ONLY (self-measured, different path); not a model term until it binds | M2-era |
| cost_per_token_per_block | 1381 cyc | 1.625 µs | c_word_roundtrip·N·(4·lpb/256), lpb=4 | derived |
| free-token ratio | 1/522 per token | clock-free | 1381 / 720,445 cyc | derived |

## Benchmark settings and results

Setting: real WSE-3 (EPCC CS-3), SDK 2.10/1.13.2; one column + 1 storage PE,
color 1 (decode reduce_1st_0 binding), GO-triggered steady-state start,
single-PE TSC deltas, blocking, verify-not-store, n=3/point, **max spread 1
cycle across every cell** (deterministic). Variables swept: E ∈
{4,32,64,128,256,512,1280} (N=256,D=1); N ∈ {32,64,128,256} × E ∈ {4,64}
(D=1); D ∈ {1,8,32} (N=256,E=64). 51 appliance jobs total; per-run wsjob ids
in `results/{2026-08-22-payload-sweep,expAC}/`. Figure:
`results/plots/expAC_model_fit.png` (commit e9e6ec8).

Key cells (cycles; µs@0.85): (256,4,1)=63,157 (74.3); (256,64,1)=1,388,470
(1,633.5); (256,512,1)=11,366,325 (13,372); (256,1280,1)=28,471,221
(33,495); (128,64,1)=694,418 (817.0); (32,64,1)=173,906 (204.6);
(256,64,32)=1,388,593 (+123 cyc vs D=1).

## Fitting conclusions

- All preregistered predictions CONFIRMED except one informative sub-claim:
  the storage EMIT span SHRANK with distance (−4.1 µs @D=32) while the full
  cycle grew by exactly 2 cyc/hop ⇒ the emit span is backpressure-coupled to
  the downstream consumer; evidence the reload serial bottleneck is the
  OWNER-side data task (Exp-B decides).
- Single linear coefficient carries ±0.9% over the whole range (true E-curve
  mildly convex below E≈64 — documented, not tuned away).
- Everything labeled AS-BUILT: the wire is ~39× under-used; coefficients
  price per-wavelet CE involvement, which the DSD variants remove.

## Update (later 2026-08-23): Exp-B verdict — owner data task WAS the reload bottleneck

- Paired device runs (commit fd94986, 12 jobs, n=3, spread ≤1 cyc): with
  owner-side bulk fabin-DSD receive, roundtrip marginal **86.87 → 56.00
  cyc/word**; park EXACTLY 43.00 both modes; reload share 43.9 → **13.00**
  = the storage @mov32 emit loop, now a clean serial measurement. Full-cycle
  speedup 1.51–1.55×. Stage model survives with corrected constants:
  reload = max(owner-consume, storage-emit 13.0, wire 0.7); baseline max was
  the owner task (43.6).
- Prereg band (73–83) was missed LOW — the old 30–40 "emit loop" estimate
  was backpressure-contaminated, exactly as Exp-C warned. Never take a
  backpressure-coupled span as a stage cost.
- **New hardware semantics [sim-observed, design now robust to it either
  way]: an input queue claimed by a pending fabin microthread does NOT
  deliver control-task activations for control wavelets arriving on that
  color** — router-level SWITCH_ADV still executes (demux kept working),
  only the CE tap vanishes. dsd variant therefore suppresses TURN taps
  (ce_ignore=1) and sends no fence; export/TSC end = read completion.
- Next as-built rungs: storage-side DSD emit (13.0 → ~wire), storage-side
  DSD park receive (43.3 → ~wire) — both required for real KV store anyway.
  cost_per_token (owner-DSD): 56×16 = 896 cyc = 1.054 µs @0.85.
