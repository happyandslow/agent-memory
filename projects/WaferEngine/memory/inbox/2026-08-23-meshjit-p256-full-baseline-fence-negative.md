# MeshJIT P=256 full-baseline host fence is not causal — 2026-08-23

**Project:** WaferEngine
**Author:** codex
**Status:** captured

## What happened / finding

- Situation: the full P=256 Attention max-only diagnostic reproducibly returned `15.015625` on all 65,536 PEs instead of the expected `19.90625`, while a longer shifted-score diagnostic was correct. A host fence between route repaint and max reduction was proposed to test collective quiescence.
- Four fresh-runtime CS-3 arms used identical seed-20260822 inputs. The original max-only arm reproduced `15.015625`; the original shifted arm, a common-helper one-RPC arm, and the same common helpers split by a synchronous host RPC fence all returned `19.90625` with zero raw-f16 max/shift mismatches.
- The one-RPC and host-fence arms were raw-bit identical for scaled score, pre-reduce local max, post-reduce global max, shifted score, and phase. Their pre-reduce local max also matched a host recomputation exactly.
- Verified negative result: a host fence is not necessary for recovery and cannot be credited as the fix. The symptom is instrumentation/call-path sensitive. Late collective visibility remains plausible because every correct path performs work after the collective, but stale channel payload mixing was not demonstrated.
- Analysis gotcha: SDK D2H arrays here are `[py, px, local_element]`; a Y-axis collective must be checked by reducing NumPy axis 0. The first on-device summary reduced axis 1 and produced invalid expected-value mismatch counts, while the saved device arrays remained valid. Offline axis-0 reanalysis produced the verdict above.

## Implications / next actions

- [ ] Preserve the original max-only call path and sample the same max storage immediately after the collective and again after controlled on-PE delay or a device-side completion sentinel, without running subtract.
- [ ] Do not use a successful host-fence run as evidence of stale channel data unless the same-instrumentation one-RPC control fails.
- [ ] When validating a CSL collective from SDK arrays, record the `[py, px, local]` host axis mapping explicitly before computing the reference.

## Pointers

- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-runtime-validation/full-baseline-fence/cs3_evidence/2026-08-23/REPORT.md`
- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-runtime-validation/full-baseline-fence/cs3_evidence/2026-08-23/corrected_results.json`
- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-runtime-validation/full-baseline-fence/cs3_evidence/2026-08-23/device_arrays_f16.npz`
- `projects/WaferEngine/memory/inbox/2026-08-23-meshjit-p256-route-repaint-minimal-negative.md`
