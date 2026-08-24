# Shared-slot validation blocked after first dynamic load — 2026-08-22

**Project:** WaferEngine
**Author:** codex
**Status:** drained 2026-08-23 into `memory/topics/meshjit-code-relocation.md`, `plan.md`, and generated views

## What happened / finding

- In `WaferLLM` shared-slot Route-A/Policy-P validation, a coherent P=8 simulator
  build passed and the original baseline completed on deterministic input.
- The first dynamic attempt completed receiver-arena H2D, `init_task`,
  holder-catalog H2D/D2H, and `d_full_load_page(page=1, epoch=1)`, then blocked
  at the immediate receiver-state D2H readback. No admitted-run or release RPC
  began.
- This establishes only the closest reverse diagnostic (receiver-state
  observation after page load); it does not establish slot-byte proof, function
  invocation, or `B_original == D_dynamic`.

## Implications / next actions

- [ ] Treat this as a runtime-validation stop point until a separately authorized
  investigation determines why receiver-state D2H cannot complete after page
  load.

## Pointers

- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-runtime-validation/results/simulator_failure.json`
- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-runtime-validation/runs/p8-v4/dynamic_host_trace.jsonl`
