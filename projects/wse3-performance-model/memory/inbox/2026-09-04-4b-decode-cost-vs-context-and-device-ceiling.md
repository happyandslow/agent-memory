# Qwen3-4B decode on CS-3: cost vs context (681K + 16 cycles/token) and the real ceiling (29,184) — 2026-09-04

**Project:** wse3-performance-model
**Author:** claude
**Status:** captured

## Situation

You need the 4B decode rate at a context other than 8K, or the longest
`MAX_SEQ_LEN` that actually runs on the appliance (the local compile sweep
said 30,464). Data: `wse3-performance-model/analyses/2026-09-04-4b-context-sweep/`
(`results/context_sweep.json`, `results/turn_estimate.json`, logs, configs,
driver); figure `assets/2026-09-04-context-sweep.png`.

## What happened / finding (measured, CS-3, route-table 4B decode tree
unmodified, bsz 1, host-ingested prefix then 4,096 decode steps)

| MAX_SEQ_LEN | context during decode | cycles/step | tok/s @750 MHz |
| --: | --- | --: | --: |
| 8,192 | 4K→8K | 785,826 | 954 |
| 16,384 | 12K→16K | 889,547 | 843 |
| 23,040 | 18.7K→22.8K | 1,029,112 | 729 |
| 28,160 | 23.8K→27.9K | 1,096,070 | 684 |
| 29,184 | 24.8K→28.9K | 1,109,064 | 676 |
| 30,464 | appliance link fails (task table / `.data.hi`) | — | — |

- **Linear: cycles/step ≈ 680,741 + 16.07 × context tokens.** 8K→29K is
  +41 % per step. Rate at 4K/8K/16K/23K/29K ≈ 1,005/923/794/714/652 tok/s.
- **Device ceiling MAX_SEQ_LEN = 29,184**; the locally compiled 30,464 does
  not link on the appliance (appliance `.text` is a few hundred bytes larger).
  Bisected with 28,160 and 29,184 (both run).
- 16 cycles per context token is ~15× the MeshRT GPT-OSS-20B long-context
  kernel (1.1 cycles per context token per step, 4K→128K): the 4B attention
  path is latency-bound per position — kernel maturity, not hardware.
- Per-turn re-estimate (Claude Code, harness capped at 29K, rate from the
  fit, prefill 9,304 tok/s): median turn **≈ 26 s** (2.7 s prefill + 22.3 s
  decode) vs the earlier 18.8 s "8K rate everywhere" estimate and ≈ 41 s
  on an H200 at 9B/4K rates (GPU side still uncapped and context-independent).

## Gotchas

- One run failed with appliance HTTP 503 (`grpc StatusCode.UNAVAILABLE`,
  `wsjob-p3ey7sbsty338c6aks3x6g`); a plain retry succeeded — treat 503 as
  transient infra, not a kernel error.
- A tmux wait-loop keyed on "C16 exit" matched the *first* (failed) C16 line
  and started the bisect early; key such waits on a line that only the run
  you are waiting for can produce.

## Pointers

- Report: `docs/reports/2026-09-04-4b-wide-layer-session-report.md` Round 16
- Related: `2026-09-03-4b-batch-scaling-pipeline-and-750mhz-clock.md`,
  `2026-09-04-4b-row-is-serial-attn-ffn-block-times.md`
