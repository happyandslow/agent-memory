# Force-decode attribution — raw measurements (2026-07-27)

Branch `lexu/staging/kv-feature` @ `ad52da0`, clean worktree (M1-S1 changes excluded).
Kernel unchanged — measurement only. Clock 1.1 GHz.

## Derivation used everywhere

Timed window `W = DECODE_LENS[-1] - WARMUP - 1`; `f` = forced steps inside it = `F - WARMUP - 1`.

```
span(F=1)   = W * C_free
span(F=big) = (W - f) * C_free + f * C_forced
=> C_free   = span1 / W
   C_forced = (span2 - (W - f) * C_free) / f
```

`DECODE_LENS` is set equal to `MAX_SEQ_LEN - PREFILL_LEN` in every device config so the
`counted_tokens` divisor in `launch.py` is exact (see the divisor bug note below).

---

## A. Device context sweep — 2x4 blocks, 524,288 PEs

Fixed: dim 2048, 28 layers over 8 blocks (`max_lpb=4`), vocab 151,936, `HT_WIDTH_tail=128`,
`P_BLOCK_SIZE=256`, bsz 1, decode window 256 steps (`W=239`), `F=209` (`f=192`).

| config | prefill | MAX_SEQ | span F=1 (cyc) | span F=209 (cyc) | free µs/tok | forced µs/tok | forced/free | speedup |
|---|---|---|---|---|---|---|---|---|
| `test_device_ctx0256_F{001,209}` | 256 | 512 | 125,985,549 | 36,579,350 | 479.2 | 55.9 | 11.7% | 8.57x |
| `test_device_ctx0768_F{001,209}` | 768 | 1024 | 129,057,460 | — | 490.9 | 57.5 | 11.7% | 8.54x |
| `test_device_ctx1792_F{001,209}` | 1792 | 2048 | — | — | 513.8 | 60.8 | 11.8% | 8.45x |
| `test_device_ctx3840_F{001,209}` | 3840 | 4096 | — | — | 560.0 | 67.4 | 12.0% | 8.31x |

Free step grows 479.2 -> 560.0 µs/tok (+17%) while **forced/free stays flat at ~12%**.
Skip-compute would require it to climb toward 100% (its saving is sequence-independent).

## B. Device pipeline-depth ablation — only block count varied

Same full size as A; `P_BLOCK_SIZE=256` held so per-PE work is identical across points.
prefill 256 / decode 256.

| config | blocks | PEs | max_lpb | free µs/tok | forced µs/tok | forced/free | pipelining pred | skip pred |
|---|---|---|---|---|---|---|---|---|
| `test_device_abl_nb4_F{001,209}` | 2x2 = 4 | 262,144 | 7 | 468.9 | 97.2 | **20.7%** | 25.0% | ~12% (flat) |
| `test_device_abl_nb8_F{001,209}` | 2x4 = 8 | 524,288 | 4 | 479.2 | 55.9 | **11.7%** | 14.3% | ~12% (flat) |

`nb2` (1x2, 14 layers/PE) **does not link**: `ran out of PE memory for data (.data.hi)` +
`(.bss)` + `ran out of PE memory for task table`.

Halving blocks: forced step x1.74, free step x0.98.

### Model fit (one free parameter)

`forced/free = (max_lpb / n_layers) * x`, `x = T_blocks / (T_blocks + T_tail)`

- **x = 0.823** => `ht_tail` is **17.8%** of a free decode step
- 4 blocks: model 20.6% vs measured 20.7% (0.4% err)
- 8 blocks: model 11.8% vs measured 11.7% (0.4% err)

**Decomposition of the 8.55x:  1.22x (skip-compute)  x  7.0x (pipelining)** = 8.51x
predicted, where `7.0 = n_layers / max_lpb = 28 / 4`.

---

## C. Simulator depth ablation (superseded by B; corroboration only)

Toy geometry `dim=64 vocab=24 n_layers=8 bsz=2`, `P_BLOCK_SIZE=8`; `W=6`, `F=6` (`f=4`).

| config | blocks | max_lpb | span F=1 | span F=6 | free cyc/step | forced cyc/step | forced/free | pipelining pred |
|---|---|---|---|---|---|---|---|---|
| `test_sim_abl_nb2_F{1,6}` | 1x2 = 2 | 4 | 581,009 | 381,909 | 96,835 | 47,060 | 48.6% | 50.0% |
| `test_sim_abl_nb4_F{1,6}` | 2x2 = 4 | 2 | 582,635 | 290,746 | 97,106 | 24,134 | 24.9% | 25.0% |
| `test_sim_abl_nb8_F{1,6}` | 2x4 = 8 | 1 | 589,709 | 247,456 | 98,285 | 12,722 | 12.9% | 12.5% |

`nb4` re-run clean after a filename race -> **bit-identical** (582,635 / 290,746).

## D. Reproduced 2026-07-23 baseline F-sweep (sim, for the record)

`test_sim_2x2blk_fsweep_F{1,2,4,6}` reproduced exactly on the clean worktree:
F=1 span 514,140; F=2 514,117; F=4 392,892; F=6 267,918 (reported 17138.0 / 17137.2 /
13096.4 / 8930.6 cyc — matches the recorded values bit-for-bit).

---

## Measurement bug (affects historical numbers)

`launch.py:238-248` computes `counted_tokens = MAX_SEQ_LEN - PREFILL_LEN - WARMUP - 1`
**before** the round loop, but the device's real step count is `DECODE_LENS[rnd]`.
When `DECODE_LENS < MAX_SEQ_LEN - PREFILL_LEN` the span is divided by the wrong count:

- S6b sim sweep: divisor 30 for a 6-step window => **absolute cyc/token ~5x too low**
- `test_device_2x4block_kv_varlen.json`: 3.14x under-report

Ratios and curve shapes are unaffected (constant factor within a sweep).

## Verification limits

Device runs are **timing-only** — `[oracle] skipped on device`, and `KV-SEED` / `LOCAL-TOPK`
are sim-only. Device-scale numerics at large F are **unverified**. Correctness is sim-verified
at F=4 (max_abs 9.8e-5) on the identical kernel. All 256 steps confirmed to execute
(`topk_args.shape = (256, 1, 20)`), ruling out "fast because steps were skipped".
Weights are mock/seeded (timing is value-independent).

## Cost

8 context-sweep runs = 29 min wall. Ablation adds 2 runs. Compile 29–54 s, decode run 17–19 s
each. Each run leaves a ~23 GB worker-side artifact dir (deleted between points).
