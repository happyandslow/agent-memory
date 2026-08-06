# Qwen3-1.7B decode pipeline-depth CS-3 profile (2026-08-06)

**Project:** WaferEngine
**Author:** codex
**Status:** drained   <!-- drained 2026-08-06 into projects/we-pr14-depth-layout topic decode-pipeline-depth-layout.md + that project's plan -->

## What happened / finding

- Base snapshot: upstream/main `b136ab64b3f5575c72fb722fb972ef5c77f4c9fe`;
  repository remote remained the `happyandslow/WaferEngine` fork.
- Compared baseline 8-stage 256x256 blocks with one-layer 28-stage 64x256
  blocks, bsz=1, device TSC at 0.85 GHz.
- Device-authoritative maximum sequence length: baseline 32,512 (32,768 is
  the signed-i8 KV-stride structural boundary); 64x256 18,688 (18,944 fails
  PE `.data.hi` and task-table memory). Candidate capacity is 57.48% of
  baseline, a 42.52% reduction.
- Shared decode-step pilot over D={64,128,256,512} selected D=64: every D was
  within 1% of D=512 for both layouts and all CVs were below 1%.
- At positions 256/1024/4096/8192/16384, baseline decode throughput was
  1850.5/1784.2/1702.1/1644.0/1538.7 tok/s; 64x256 was
  1425.4/1380.7/1314.3/1259.4/1162.2 tok/s. The deeper layout is 22.6--24.5%
  slower. Baseline-only tail: 1378.1 tok/s at 24,576 and 1317.7 at 32,000.
- Dedicated prefill best config is position-dependent. c512 wins at 256/1024
  (4532.2/13761.8 tok/s); production c768 wins at 4096/8192
  (23583.6/24700.2 tok/s). All numbers are 0.85 GHz device TSC.
- Nominal-depth decode-side pipeline-prefill numbers are upper bounds, not
  measurements: baseline roughly 13--15k tok/s and 64x256 roughly 35--40k
  over matched positions. Dedicated prefill is the achieved comparison.
- At position 256 specifically, the nominal-depth arithmetic is
  `1850.5 * 8 = 14,804.0 tok/s` for the baseline and
  `1425.4 * 28 = 39,911.2 tok/s` for 64x256 (2.696x the baseline estimate).
  This multiplication assumes all pipeline stages accept independent prefill
  tokens at the measured steady-state decode initiation interval, with no
  fill/drain, dependency, collective, input, or output bottleneck. It must not
  be reported as achieved throughput without an actual pipelined-prefill run.
- Local SDK 2.10 sim artifacts and CS-3 appliance/server 1.13.2 device
  artifacts are not byte-identical; source/config hashes match. Device
  artifacts and device measurements are authoritative.

## Reusable execution lessons

- `SdkLauncher.run()` returns stdout but does not automatically retain worker
  files. Download `run_summary.json` and a compact compiled-artifact manifest
  with `download_artifact()` before leaving the same launcher context; a new
  launcher cannot recover the old ephemeral worker output.
- Decode summaries store `config` as the artifact directory, commonly prefixed
  with `out_`; layout inference must handle that controlled prefix.
- Current dedicated-prefill verdicts use `tsc.per_round`; readers should also
  accept the older `per_round_tsc` form.
- CS-3 sync deletion can remove ignored remote results. Copy every device-
  authoritative result locally before the next sync.

## Implications / next actions

- [ ] Test the remembered 128x128 one-layer layout.
- [ ] Investigate changing HT geometry/size to relieve embedding SRAM pressure.
- [ ] If one-layer layouts remain unsuitable, test a two-layer rectangular layout.
- [ ] Validate the decode-derived pipeline-prefill upper bound with an actual
  multi-token pipelined-prefill implementation before reporting it as achieved.

## Pointers

- ContextBase log:
  https://context.ed-aisys.com/doc/2026-08-06-result-qwen3-17b-decode-pipeline-depth-profile-tWZ5gVLrVO
- Primary report and raw paths:
`/home/lexu/we-pr14-depth-layout/docs/DECODE_PIPELINE_DEPTH_EXPERIMENT_2026-08-05.md`
and
`/home/lexu/we-pr14-depth-layout/models/qwen3_1p7b-decode/bench/results/`.
