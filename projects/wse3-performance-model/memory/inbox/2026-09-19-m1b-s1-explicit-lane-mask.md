# Explicit lane completion control — 2026-09-19

**Project:** wse3-performance-model (session workspace; code belongs to WaferEngine-staging)
**Author:** codex
**Status:** captured

## What happened / finding

- When designing M1b-S1 so a short request can complete on EOS while peers continue, Le explicitly asked to add an explicit lane mask to the design. The accepted direction propagates execution status with activations through head and decode blocks, rather than inferring completion from pad embeddings.
- The mask must reach relevant PEs before the next forward. The EOS-producing forward remains valid; subsequent KV/cursor/RoPE updates for that lane stop. Request completion does not depend on replacement/admission.

## Implications / next actions

- Use the source-linked design below for the file/function change map. Exact encoding, packet extents, resource costs, compute-skip coverage, and the complete verification contract remain under review. Acceptance of this direction is not acceptance of those details or evidence of implementation/device correctness.

## Pointers

- Authority: Le's 2026-09-19 instruction to include the annotated explicit-mask proposal in the design.
- `/home/lexu/WaferEngine-staging/docs/analysis/2026-09-19-m1b-s1-per-lane-completion-design.md`
- Existing objective capture: `2026-09-18-m1b-s1-independent-completion-target.md` in this inbox.
