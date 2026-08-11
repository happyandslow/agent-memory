---
summary: Qwen3 force-decode-as-prefill throughput measurements were corrected after host D2H receive scheduling backpressured the WSE program; co-drain protocol restores the 28-stage advantage.
tags: [WaferEngine, qwen3, force-decode, prefill, throughput, backpressure, cs3, drained-inbox, 2026-08-09]
---

# Qwen3 force-prefill output-backpressure correction — 2026-08-09

This topic was created by the 2026-08-11 maintain pass from the paired dated inbox captures. Keep it as the durable home for the corrected result; the 2026-08-08 capture is retained only as the superseded protocol-failure record.

## Finding

A force-decode-as-prefill benchmark first appeared capped near 12–13.6K tok/s and made the 28-stage layout look slower than the 8-stage layout. That was a host protocol artifact, not a kernel throughput result: the host synchronously sent all teacher-forced X vectors before posting any logits/TSC receive, while the device emitted one output record per step. The unarmed D2H sink filled finite buffers and propagated flow-control backpressure into the device-TSC interval.

Correct protocol: pre-post one nonblocking receive for the full round's output records plus the final 16-u32 TSC burst before KV/X ingress; after sending X, wait for the receive and parse the identical ordered bytes. Kernel source, causal computation, and TSC points are unchanged.

## Corrected result

Under the co-drain protocol, corrected N=1024 force throughput is:

| Prefix | 8-stage tok/s | 28-stage tok/s | 28-stage / 8-stage |
|---:|---:|---:|---:|
| 256 | 15,872.9 | 46,858.4 | 2.952x |
| 1,024 | 15,260.0 | 45,378.2 | 2.974x |
| 4,096 | 14,703.2 | 43,478.0 | 2.957x |
| 8,192 | 14,095.3 | 41,341.4 | 2.933x |
| 16,384 | 12,924.6 | 37,433.2 | 2.896x |

Additional interpretation:

- N=1024/N=512 force ratio under the same co-drain harness is 0.984–0.999 for 8-stage and 0.992–1.002 for 28-stage, so there is no meaningful decoding-length regression.
- Force/(same-run ordinary × stages) is 106.6–110.9% for 8-stage and 115.3–119.2% for 28-stage. Do **not** turn this into a negative physical bubble fraction: forced tokens skip final RMSNorm/lm_head/top-K/sampling on intermediate tokens, while ordinary decode includes that tail work.
- Corrected N=1024 force vs best dedicated prefill: 28-stage is 10.34x / 3.30x / 1.84x / 1.67x at prefixes 256/1024/4096/8192.
- Maximum force CV was 0.00291% for corrected N=512 and 0.00223% for corrected N=1024. Local/device final SHA manifests matched. `MAX_SEQ_LEN=17408` passed a device compile-only probe and covers 16384+1024.

## Operational lesson

For any bidirectional SdkLayout throughput measurement, pre-post the D2H receive when the device emits per-step output inside the timed window. Device TSC can include host-induced fabric stalls when host receive scheduling lets output buffers fill; host X-send wall time is not evidence that the wafer stayed unblocked.

## Superseded interpretation

The 2026-08-08 capture and ContextBase report that claimed a 62–74K cycle/token kernel floor, a 12–13.6K tok/s force floor, or a 28-stage loss versus 8-stage are superseded. The late-drain raw measurements remain useful only as a host/device protocol backpressure demonstration.

## Pointers

- Corrected ContextBase page: `https://context.ed-aisys.com/doc/2026-08-09-corrected-result-qwen3-17b-force-decode-as-prefill-CVoQosPFDs`
- Corrected report: `/home/lexu/experiments/qwen3-force-perf-n1024-codrain-20260809/results/20260809T0309Z_force_prefill_n1024_codrain/README.md`
- N=1024 aggregate: `aggregate/comparison.{json,csv}` under that result directory.
- Corrected N=512 aggregate: `aggregate_n512/comparison.{json,csv}`.
- Same-harness trend: `aggregate/n512_vs_n1024_codrain.csv`.
- Late-drain N=1024 raw result: `/home/lexu/experiments/qwen3-force-perf-n1024-20260809/results/20260809T0229Z_force_prefill_perf_n1024`.
- Source captures: `memory/inbox/2026-08-08-qwen3-force-decode-as-prefill-throughput.md`, `memory/inbox/2026-08-09-qwen3-force-prefill-output-backpressure-correction.md`.
