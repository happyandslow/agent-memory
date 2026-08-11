# Full-model M1-S3.7 reuse benchmarks and batch-capacity boundary — 2026-08-11

**Project:** WaferEngine-staging
**Author:** codex
**Status:** captured

## What happened / finding

- When evaluating M1-S3.7 reuse performance, use real CS-3 TSC rather than simulator timing or host wall. The full Qwen3-1.7B geometry was `dim=2048`, 28 layers, 16/8 GQA, `Pw=512`, `Ph=1024`, `P_BLOCK_SIZE=256`, and `MAX_SEQ_LEN=1792`.
- Reuse-length sweep, three appliance repetitions per point: at `bsz=1`, partial `R=256/512/768` improved the 245.285M-cycle miss to 210.731/176.171/155.839M cycles (1.164×/1.392×/1.574×); exact `R=256/512/768/1024` with `F=1,G=255` took 134.928/136.479/138.011/139.652M cycles (1.818×/1.797×/1.777×/1.756×). At `bsz=2`, the corresponding miss was 290.696M; partial was 255.852/221.281/189.308M (1.136×/1.314×/1.536×), and exact was 166.345/167.239/168.100/169.139M (1.748×/1.738×/1.729×/1.719×). Most relative sample SDs were below 0.1% (maximum 0.443%).
- Synthetic temporal-locality sweep used fresh sequence IDs and multiple 256-token prefix groups. With `SLOT_COUNT=2`, W2 produced 8 hits/2 misses and 188.503M cycles, but W3/W5/no-reuse all thrashed at about 355M. With `SLOT_COUNT=4`, W3 retained seven prefixes and improved from the matching 355.008M no-reuse control to 209.696M cycles (1.693×); W5 still thrashed at 355.218M. Slots help when capacity crosses the locality working-set threshold, not merely because the configured count is larger.
- The unchanged full-model kernel compiles/runs at coupled `bsz=SLOT_COUNT=1,2`, but `3` and `4` fail before execution from `ht_tail` shared PE data-SRAM exhaustion. M4's known lower bound is already about 39,648 B/PE (19,008 B fixed lm-head tile + 19,008 B fp32 partials + top-k/merge/state), before compiler/DSD overhead. Task-table and decode dcache messages are cascade/secondary. These failures have no TSC or ledger and are capacity-boundary evidence, not performance rows.
- Long appliance sweeps observed eight strict pre-worker HTTP-502 attempts in A (8/56 launches) and one in B. Each had zero worker/TSC/ledger evidence, was archived, cooled down for 300 s, and retried unchanged; only complete retry evidence was counted. A server-side `SUCCEEDED` state alone was insufficient when the client failed to retrieve TSC.

## Implications / next actions

- [ ] M1-S5 must separate batch size from slot count and include `ht_tail` batch scratch in the SRAM model; reducing decode `MAX_SEQ_LEN` alone cannot fix the observed bsz≥3 compile boundary.
- [ ] Preserve the device-TSC comparisons as the current S3.7 performance baseline; do not use host-wall launch time or simulator TSC as a replacement.
- [ ] For future long CS-3 sweeps, classify only zero-worker/zero-TSC HTTP 502 as retryable, archive it, wait about 300 s, and retry the identical logical point without counting the failed attempt.

## Pointers

- `/home/lexu/WaferEngine-staging/milestones/M1-intra-pe-reuse.md`
- `/home/lexu/.claude/jobs/bfd14235/tmp/results.jsonl`
- `/home/lexu/.claude/jobs/bfd14235/tmp/expA_M1_summary_at24.json`
- `/home/lexu/.claude/jobs/bfd14235/tmp/expA_summary_M2_at48.json`
- `/home/lexu/we-m1-s3-perf-b/models/qwen3_1p7b-decode/exp_b/results/summary.csv`
- `/home/lexu/we-m1-s3-perf-b/models/qwen3_1p7b-decode/exp_b/results/report.md`
