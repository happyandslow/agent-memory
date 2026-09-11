# Distinguishing expected layout rounding from downstream errors — 2026-09-11

**Project:** wse3-performance-model
**Author:** codex
**Status:** captured

## What happened / finding

- For comparisons where changed PE dimensions alter local accumulation and collective order, Le requested matching the results of those sensitive steps before testing other computations.
- The delegated offline replay supplies canonical upstream FP32 results at sensitive boundaries, checks deterministic intermediates before later replacements, and rejects a BF16-bit fault before the following DOWN injection. Four full-dimension, 33-step comparisons (integer/random × square128/tall128) pass 6,668 checkpoint instances each. Replacement-disabled models still match the six prior CS-3 output arrays exactly.
- This is analytical evidence with shared source-derived arithmetic helpers. No new on-device intervention ran; host ownership/count replay does not certify actual fabric movement. Do not mark the complete group or device intermediate gate passed from this report.

## Implications / next actions

- Retain native-order checks for sensitive operations and exact checks for deterministic work on aligned inputs. Future device probes must exercise actual routes and read recipients before replacing subsequent state.

## Pointers

- [Output doc and companion evidence/reproduction artifacts](/home/lexu/wse3-performance-model/docs/reports/2026-09-11-layoutC-aligned-step-validation-output.md).
