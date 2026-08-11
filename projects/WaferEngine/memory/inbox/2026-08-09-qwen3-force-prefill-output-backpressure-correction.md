# Qwen3 force-prefill output-backpressure correction — 2026-08-09

**Project:** WaferEngine
**Author:** codex
**Status:** drained
**Drained to:** `memory/topics/qwen3-force-prefill-output-backpressure.md` (2026-08-11)

## What happened / finding

- Situation: force-decode-as-prefill appeared capped near 12-13.6K tok/s and the 28-stage layout appeared slower than 8-stage. Increasing N from 512 to 1024 initially reduced measured force throughput to 8.4-8.9K tok/s.
- Root cause: the host synchronously sent all F teacher-forced X vectors before posting any logits/TSC receive. The device emitted one output record per step, so D2H backpressure entered the device-TSC interval. Host X-send wall time did not detect this because send submission/ingress headroom is not proof that the unarmed output sink cannot stall the wafer.
- Fix/measurement protocol: pre-post one full-round `runtime.receive(..., nonblock=True)` for all N token records plus the 16-u32 TSC burst before KV/X ingress; after X sends, `runtime.task_wait` and parse the identical ordered bytes. Kernel source, causal computation, and TSC points are unchanged.
- Device evidence: pilot N=1024 prefix256 moved 8-stage 8.82K -> 15.87K tok/s and 28-stage 8.41K -> 46.85K tok/s. Two corrected full matrices were then run under one host protocol: N=512/F=512 and N=1024/F=1024, five prefixes, ordinary+force, five interleaved repeats, 200/200 rounds valid total.
- Corrected N=1024 8-stage force: 15.873 / 15.260 / 14.703 / 14.095 / 12.925 K tok/s at prefixes 256/1024/4096/8192/16384.
- Corrected N=1024 28-stage force: 46.858 / 45.378 / 43.478 / 41.341 / 37.433 K tok/s.
- N=1024/N=512 force ratio under the same co-drain harness: 0.984-0.999 for 8-stage and 0.992-1.002 for 28-stage. There is no meaningful decoding-length regression.
- 28-stage/8-stage force ratio is 2.896-2.974x for N=1024. The deeper layout has a real advantage once output backpressure is removed.
- Force/(same-run ordinary x stages) is 106.6-110.9% for 8-stage and 115.3-119.2% for 28-stage. This does not imply negative physical bubbles: force skips final RMSNorm/lm_head/top-K/sampling on intermediate tokens, so ordinary x nominal stages is a scale estimate, not a physical upper bound.
- Corrected N=1024 force vs best dedicated prefill: 28-stage is 10.34x / 3.30x / 1.84x / 1.67x at prefixes 256/1024/4096/8192.
- Maximum force CV: 0.00291% for corrected N=512 and 0.00223% for corrected N=1024. Local/device final SHA manifests match. MAX_SEQ_LEN=17408 passed a device compile-only probe and covers 16384+1024.
- The 2026-08-08 capture and ContextBase report claiming a 62-74K cycle/token kernel floor are superseded. Those raw late-drain measurements remain useful only as a host/device protocol backpressure demonstration.

## Knowledge-base correction

- Corrected result page: `https://context.ed-aisys.com/doc/2026-08-09-corrected-result-qwen3-17b-force-decode-as-prefill-CVoQosPFDs`
- The 2026-08-06 decode pipeline-depth profile's follow-up section now retracts the late-drain conclusion and points to the corrected result.
- The superseded 2026-08-08 agent-memory capture is retained only as a compact protocol-failure record; its former kernel-floor interpretation was removed.

## Implications / next actions

- [x] Correct the existing ContextBase result page and the downstream 2026-08-06 profile that cited the 12-13.6K floor or said 28-stage loses to 8-stage.
- [ ] Treat D2H sink pre-posting as mandatory for any bidirectional SdkLayout throughput measurement; device TSC can include fabric stalls caused by host receive scheduling.
- [ ] Do not report a physical pipeline bubble fraction from `1 - force/(ordinary x stages)` because ordinary and forced tokens perform different tail work; add per-stage timestamps if physical bubbles are required.

## Pointers

- Corrected report: `/home/lexu/experiments/qwen3-force-perf-n1024-codrain-20260809/results/20260809T0309Z_force_prefill_n1024_codrain/README.md`
- N=1024 aggregate: `aggregate/comparison.{json,csv}` under that result directory.
- Corrected N=512 aggregate: `aggregate_n512/comparison.{json,csv}`.
- Same-harness trend: `aggregate/n512_vs_n1024_codrain.csv`.
- Late-drain N=1024 raw result: `/home/lexu/experiments/qwen3-force-perf-n1024-20260809/results/20260809T0229Z_force_prefill_perf_n1024`.
- Superseded capture: `projects/WaferEngine/memory/inbox/2026-08-08-qwen3-force-decode-as-prefill-throughput.md`.
