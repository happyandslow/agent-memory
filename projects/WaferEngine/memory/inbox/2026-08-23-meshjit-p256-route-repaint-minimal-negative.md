# MeshJIT P=256 route-repaint minimal reproducer is negative — 2026-08-23

**Project:** WaferEngine
**Author:** codex
**Status:** captured

## What happened / finding

- Situation: the full P=256 Attention diagnostic returned a uniform group-11 partial max (`15.015625`) in one baseline RPC, while a longer shifted-score RPC produced the correct shifted output. This raised the hypothesis that X→Y collective route repaint lacked quiescence.
- A standalone CS-3 reproducer used the exact frozen production `comm_pe.csl` (`e56d46853c4228ba23f05d840ed764c95001a432ad1ae11091aadf16f898b1cc`), the real 256×256 PE geometry, and the production communication extents: Y-axis 48-f16 QKV sum-allreduce, repaint X, X-axis 16-f16 score sum-allreduce, repaint Y, then scalar max-allreduce.
- Four fresh-runtime conditions all returned raw-f16 `255.0` on all 65,536 PEs with zero mismatches: immediate, 64 local-delay iterations, 4096 local-delay iterations, and a two-RPC host fence.
- Verified negative result: route repaint, the production collective implementation, and production message extents are not sufficient by themselves to reproduce the partial maximum. The immediate arm already passed, so this experiment cannot show whether delay or a fence repairs the full Attention path.
- This narrows the missing trigger to state omitted by the standalone program: the real Attention computation/DSD/DSR state, exact data, code layout/call path, or another full-prefix resource interaction. The earlier inbox note's reciprocal-implementation explanation is superseded as a leading hypothesis by later substep localization; it must not be treated as established root cause.

## Implications / next actions

- [ ] Insert the same two-RPC host fence into the already-failing full P=256 baseline immediately between `reconfig_allreduce_axis(1)` and `validation_diag_compute_max()`.
- [ ] In that same execution, read back both `local_max` and shifted score so a correct shifted tensor is not used as an indirect proxy for the max value.
- [ ] Do not conclude that route/collective quiescence is the root cause from the prior path-sensitive diagnostics alone.

## Pointers

- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-runtime-validation/minimal-repro/p256-route-repaint-max/cs3_evidence/2026-08-23/REPORT.md`
- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-runtime-validation/minimal-repro/p256-route-repaint-max/cs3_evidence/2026-08-23/device_results.json`
- `projects/WaferEngine/memory/inbox/2026-08-23-meshjit-p256-cs3-bitexact-failure.md`
