# What the GPU verifier's 17 ms actually measures (and the per-rank summing trap) — 2026-09-10

**Project:** nc_service
**Author:** claude
**Status:** captured

## The situation this applies to

You are about to quote, compare or decompose the GPU-side verify latency —
"32-token verify ≈ 17 ms on 8×H100" — against a draft-side number, an H20
figure, the vanilla-decode TPOT, or a whole decode-round budget. The number
comes from server log lines emitted with `SGLANG_LOG_SPEC_VERIFY_FORWARD_TIME=1`:

```
Spec verify forward timing: bs=1 verify_tokens=32 cuda_graph=True host_ms=17.2 gpu_ms=17.1
```

Before that number can carry any comparison, you need to know what it brackets
and how the rows are structured — the log gives no hint, and the obvious
readings are wrong in two different directions.

## What happened / finding

Read from the timing code actually running in the pod (`eagle_worker_v2.py`
in the fork at `/tmp/sglang-unit/python`, not stock `/sgl-workspace`):

- **`gpu_ms` is a CUDA-event bracket around exactly one thing** — the target
  model's verify forward (`target_worker.forward_batch_generation(...,
  is_verify=True)`): `start_event.record()` → forward → `end_event.record()` →
  `torch.cuda.synchronize()` → `start.elapsed_time(end)`. It therefore
  **excludes the draft RPC, sampling and scheduling**. It is not a decode-step
  latency and must not be compared against one.
- **Every TP rank logs its own row, and the ranks run in parallel.** 8 ranks ×
  63 steps = 504 rows for one 64-token generation. ~17 ms is the cost of that
  forward, **not** a per-rank slice to be summed (8×17 ms would be wrong by 8×).
  For a step-level figure take the **max over the 8 ranks per step** (they must
  sync), which is slightly higher than the pooled p50.
- `host_ms` is `perf_counter` over the same region and lands ~0.08 ms above
  `gpu_ms` — i.e. launch/sync overhead is negligible and the forward is
  GPU-bound. That closeness is why an earlier pass that accidentally pooled
  `host_ms` and `gpu_ms` rows together still got the right answer; don't rely
  on it, filter to `gpu_ms`.

Clean `gpu_ms`-only stats, 504 rows, warmup dropped (real Kimi K2.5 INT4,
TP=8, bs=1, `cuda_graph=True`, 32 draft tokens — see
[[2026-07-15-kimi-k25-h100-KNOWN-GOOD-startup-recipe]] for the run):

| lens | p50 | p90 | p99 | mean | min/max |
|---|---|---|---|---|---|
| `gpu_ms` pooled over 8 ranks | 16.96 | 17.45 | 18.55 | 16.99 | 15.25 / 22.17 |
| `host_ms` pooled (control) | 17.04 | 17.52 | 18.63 | 17.07 | 15.34 / 22.26 |
| per step, slowest of 8 ranks | **17.28** | 17.83 | 22.17 | 17.42 | 15.79 / 22.17 |

Conditions worth carrying with the number: the EIDF `eidf230ns` 8×H100 pod is
**NVSwitch all-pairs NVLink** (`nvidia-smi topo -m` shows `NV18` for every
GPU pair, 18 links × 26.562 GB/s ≈ 478 GB/s per GPU unidirectional), so the
TP=8 all-reduce inside that forward is cheap. A PCIe-interconnected 8-GPU box
would not reproduce ~17 ms.

## Implications / next actions

- [ ] When quoting the verify number next to a draft or transport number, use
      the per-step max-over-ranks lens (17.28 ms p50), not the pooled p50.

## Pointers

- Timing code: `eagle_worker_v2.py` under `/tmp/sglang-unit/python` in pod
  `kimi-k25-sglang-h100-bdwk4`, ns `eidf230ns` (ephemeral `/tmp` — the fork
  disappears if the pod restarts).
- Related: [[2026-07-15-kimi-k25-h100-KNOWN-GOOD-startup-recipe]] (the 17 ms
  headline and the break-even math built on it),
  [[2026-07-15-gpu-verify-service-eidf-k8s-VALIDATED]],
  [[specdec-d2h-latency]] (the transport leg this gets composed with).
