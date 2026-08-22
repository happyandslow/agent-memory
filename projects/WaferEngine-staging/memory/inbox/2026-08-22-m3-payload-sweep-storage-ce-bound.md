# M3 round-boundary offload/reload cost is storage-CE-bound, not wire-bound — 2026-08-22

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured

## Situation this applies to

Estimating or optimizing the cost of M3 Mode-L round-boundary KV park/reload
(one compute column -> lower-edge storage PE and back), or any design that
prices T1 on-chip movement off the 3.91 GB/s single-link figure. Also: any
protocol timing measurement on SdkLayout probes whose cycle "starts at boot".

## Setting (fully reproducible)

- `models/qwen3_1p7b-decode/bench/m3_park_band/column_cycle_demo/` at work-repo
  commit **48467e5** (sweep code) / results committed at **facc8c4**, branch
  `lexu/staging/m3-on-chip-kv-offload-study`.
- Real WSE-3 (EPCC CS-3), SDK 2.10 client / 1.13.2 cluster. N=256 compute PEs
  (decode block height) + 1 storage PE, one color (1, decode reduce_1st_0
  binding IQ3/OQ3), blocking round-end, single lane, storage verifies (does
  not store). Payload E ∈ {4,32,64,128,256,512,1280} u32 words/PE
  (E = L/16 at lpb=4), n=3 per point, 21 appliance jobs, per-run metadata
  (wsjob id, source md5s, params) in `results/2026-08-22-payload-sweep/`.
- Timing: single-PE 48-bit TSC deltas only (no cross-PE alignment): P0
  full cycle (park-send start -> fence landing), storage park span and emit
  span. Cycles -> time at **1.1 GHz** (WaferEngine constant, not SDK's 0.85).
- **Cycle start = host GO wavelet broadcast after runtime.run()** (color 9
  input stream, tap-and-forward down the column, idempotent setup()).
  Gotcha that forced this: timing from each PE's init task measured **~90 ms
  of per-PE load skew** (device E=32: 91,684 µs vs 614 µs after the fix) —
  never time an SdkLayout protocol from boot.

## Result (device, deterministic: every n=3 repetition cycle-identical)

| E | full cycle | park span | emit span |
|---|---|---|---|
| 4 | 57.4 µs | 43.4 | 12.8 |
| 32 | 614.3 µs | 324.5 | 256.7 |
| 512 | 10,333.0 µs | 5,128.0 | 5,162.4 |
| 1280 | 25,882.9 µs | 12,813.6 | 13,026.0 |

- Perfectly linear for E ≥ 32: **marginal = 20.247 µs per word-per-PE**,
  decomposing exactly into park 10.01 + emit 10.24 (the cycle IS those two
  serial phases). Floor ≈ 57 µs/cycle at tiny payload.
- **Pre-registered wire-bound model REFUTED**: prediction was 0.524 µs/word
  (2×1024 B across the bottleneck edge at 3.91 GB/s); measured 20.25 µs =
  39× slower. Mechanism located: **storage CE per-wavelet costs** — ~43
  cycles per park wavelet (data-task automaton) + ~44 cycles per reload
  wavelet (synchronous @mov32 emit loop). Effective per-column payload rate
  ≈ **101 MB/s AS-BUILT** vs ~3.91 GB/s wire ceiling. Do not quote 101 MB/s
  as a physical cost — the lever is removing per-wavelet CE involvement at
  storage (fabin-DSD bulk receive / DSD block emit).
- Model form: `t_cycle(L) ≈ 57 µs + 1.265 µs × L` at lpb=4 (E=L/16). In free
  decode tokens (654.95 µs): L=512 -> 0.94 tok, L=2048 -> 3.9, L=8192 ->
  15.8, L=20480 -> 39.5.

## Implications / next

- [ ] Storage-side DSD bulk-receive variant (also the real KV-store step):
      measures how much of the 39× headroom is realizable.
- M3 cost-model entries citing this must carry the **as-built** label and the
  per-wavelet CE mechanism, mirroring M2's as-built-vs-ceiling discipline.
