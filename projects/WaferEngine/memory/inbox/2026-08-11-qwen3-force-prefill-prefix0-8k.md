# Qwen3 force-prefill prefix-0 8K measurement — 2026-08-11

**Project:** WaferEngine
**Author:** codex
**Status:** drained

## What happened / finding

- A decode-as-prefill run with zero initial tokens cannot be enabled by only relaxing the host guard. The KV adaptor and injector otherwise execute one nonexistent segment when `n_segs_rt == 0`, and the decode block constructs zero-length KV ingress movements. A validated metadata-only path must explicitly finish/advance adaptor rows, complete injector row-sync, and skip block K/V phases after metadata.
- Device correctness gate passed at prefix 0: ordinary D64 followed by replay-force D64 had exact final valid top-k IDs and bit-identical top-k values. Intermediate forced steps intentionally skip lm_head/top-k and are not valid output oracles; sampled IDs also depend on non-reset RNG state.
- CS-3, bsz=1, prefix=0, N=F=8192, 0.85 GHz, five repeats: 8-stage steady 14,882.69 tok/s and device end-to-end 13,682.74 tok/s; 28-stage steady 44,185.79 tok/s and device end-to-end 34,872.31 tok/s; native prefill c768 device TSC 24,700.52 tok/s. Thus 28-stage device end-to-end is 1.412x native and 2.549x 8-stage; 8-stage is 0.554x native.
- Final-hop SSH reuse matters separately from gateway reuse. The old runner defaulted to `CS-3`, whose effective config had no ControlMaster, so every run opened a fresh gateway-to-CS-3 connection. `cs3-runner` now defaults runner/sync/jobs to `CS-3-cmd` and verifies a final-hop ControlMaster before long runs. This procedural lesson was applied directly to the shared skill.

## Implications / next actions

- [ ] Curate the prefix-0 result into the existing Qwen3 force-prefill topic and supersede any prefix-0 estimate with the measured end-to-end number.
- [ ] Decide whether the metadata-only prefix-0 support should be ported from the isolated experiment snapshot into the maintained decode implementation.

## Pointers

- `/home/lexu/experiments/qwen3-force-prefill-p0-n8192-20260811/results/aggregate_raw.json`
- `/home/lexu/experiments/qwen3-force-prefill-p0-n8192-20260811/results/remote_force/`
- `/home/lexu/experiments/qwen3-force-prefill-p0-n8192-20260811/results/remote_prefill/`
- `/home/lexu/claude-skills/cs3-runner/`
