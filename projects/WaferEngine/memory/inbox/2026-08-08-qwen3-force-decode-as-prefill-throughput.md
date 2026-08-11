# Qwen3-1.7B force-decode-as-prefill throughput on CS-3 (2026-08-08)

**Project:** WaferEngine
**Author:** claude (perf implementation/operations agent)
**Status:** superseded
**Superseded by:** `2026-08-09-qwen3-force-prefill-output-backpressure-correction.md`

## Correction

This experiment's force-throughput numbers are not kernel-throughput results. The host synchronously sent every teacher-forced X vector before posting the output receive. Because the device emits one output record per token, the unarmed D2H sink filled finite output buffers and propagated flow-control backpressure through the output path into the device pipeline. Device TSC correctly included those host-induced stalls.

The former conclusions that force throughput had a 12-13.6K tok/s kernel floor, that the 28-stage layout was slower than the 8-stage layout, and that the 28-stage layout achieved only 28.7-38.2% of `ordinary decode x stages` are withdrawn.

The raw late-drain measurements remain useful only as evidence that host receive scheduling can backpressure a WSE program even when timing is measured with device TSC.

## Superseded run provenance

- Result directory: `/home/lexu/experiments/qwen3-force-perf-20260808/results/20260808T2115Z_force_prefill_perf`
- Matrix: 8-stage versus 28-stage; prefixes 256/1024/4096/8192/16384; N=512; five interleaved repeats.
- Correctness precondition passed the strict full-device causal KV oracle.
- The source/config and raw results are preserved; only their performance interpretation is superseded.

## Correct protocol and corrected result

Pre-post one nonblocking receive for all N output records plus the final TSC burst before sending KV/X, then wait for that receive after ingress completes. This drains output concurrently without changing the kernel, causal computation, or TSC points.

Under that protocol, the corrected N=1024 force throughput is:

| Prefix | 8-stage tok/s | 28-stage tok/s | 28-stage / 8-stage |
|---:|---:|---:|---:|
| 256 | 15,872.9 | 46,858.4 | 2.952x |
| 1,024 | 15,260.0 | 45,378.2 | 2.974x |
| 4,096 | 14,703.2 | 43,478.0 | 2.957x |
| 8,192 | 14,095.3 | 41,341.4 | 2.933x |
| 16,384 | 12,924.6 | 37,433.2 | 2.896x |

See `2026-08-09-qwen3-force-prefill-output-backpressure-correction.md` for the complete corrected interpretation and artifact pointers.
