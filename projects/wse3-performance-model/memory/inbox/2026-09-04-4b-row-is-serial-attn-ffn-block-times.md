# Qwen3-4B decode: a block row is one serial resource; ATTN 127K + FFN 50K cycles per token — 2026-09-04

**Project:** wse3-performance-model
**Author:** claude (subagent `4b-block-tsc`)
**Status:** captured

## Situation

You are estimating forced-decode ("decoder as prefiller") or pipelined
throughput for the 4B role-split decode kernel and need to know whether the
ATTN block and FFN block of a row can work on different tokens at the same
time, and how a row's time splits between them. Write-up with every
number labelled: `wse3-performance-model/analyses/2026-09-04-4b-block-tsc/README.md`;
patch `block-tsc.patch` (adds `src/prof_tsc.csl`, new collector streams
only; verified to apply to the tracked tree; nothing committed).

## What happened / finding (measured, CS-3 `wsjob-tp5yqatuwy2mfzoubusxnc`,
`device_2x4_8k` + `device_prefill4k`, last 512 of 4,096 steps, ~8K context)

- Row 0 per token: **T_attn = 127,301 cycles** (14,145 per layer, 9 layers
  + A multicasts), **T_ffn = 50,238 cycles** (5,582 per layer); step period
  808,995 cycles (1,079 µs at 750 MHz). ATTN waits on FFN 44,981 cycles per
  token, FFN waits on ATTN 113,313; hop pair ≈ 60 cycles per layer.
- **ATTN and FFN cannot overlap across tokens**: within a row they
  alternate per layer on the same token (`decode.csl:attn_step` blocks in
  `multicast_recv_b` for FFN layer l before starting l+1). A row is one
  serial resource of T_attn + T_ffn = 177.5K cycles; today (autoregressive)
  row 0 is busy only 21.9 % of the step period.
- **Forced-decode throughput of the current kernel = 750 MHz / 177.5K =
  4,224 tok/s** (matches the two-wafer demo's 166K-cycle row period and
  Le's "single-stream × 4 stages" rule). 750 MHz / max(T_attn, T_ffn) =
  5,892 tok/s needs a kernel change making ATTN and FFN independent
  stages.
- ATTN is 72 % of a layer (same as the 9B mixer/FFN split of 69–77 %).
  Σ(8 blocks) = 87.8 % of the period; the 12.2 % residual is HT head/tail
  + inter-row K-pipe (not stamped). Whole-run FFN step period matches the
  ht_tail per-token TSC to 0.20 %.
- Gates: token records byte-identical to the 09-02 unmodified run;
  per-token TSC −0.058 %; negative control (stamp before the work) drops
  block busy to a few hundred cycles and is rejected by the 2,000-cycle
  floor check.

## Gotchas

- `<time>.get_timestamp` needs `--max-inlined-iterations ≥ 16`; the 4B
  `cslc-driver` wrapper caps it at 8. Raising it is code-neutral (the
  unmodified `decode.csl` links to a byte-identical 64,288 B ELF at 8 and
  16).
- Stamping one PE per block with its own monotonic counter avoids any
  cross-PE TSC reference correction; egress via new RAMP→NORTH bursts into a
  routing-only `kv_fwd.csl` collector at y=0 keeps existing data paths
  untouched. Instrumented ATTN r0 PEs still have 8,400 B free.

## Pointers

- Report: `docs/reports/2026-09-04-4b-wide-layer-session-report.md` Round 13
- Related: `2026-09-04-meshrt-9b-layer-time-flat-in-region-size.md`,
  `2026-09-03-4b-batch-scaling-pipeline-and-750mhz-clock.md`
