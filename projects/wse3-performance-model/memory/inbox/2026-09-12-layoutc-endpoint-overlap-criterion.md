# LayoutC endpoint overlap criterion — 2026-09-12

**Project:** wse3-performance-model
**Author:** codex
**Status:** captured

## What happened / finding

- When comparing A3->A1 sender-sweep orders, Le requested separating strip
  router behavior from compute-PE injection/receipt. Keep router-only transit;
  compare upstream-first versus own-first later on the same value contract.
- Le's evaluation priority is to overlap independent CE<->router transfers and
  keep shared links occupied, avoiding unnecessary sequential endpoint work.
  Small-message RAMP overhead versus large-message bandwidth dominance is the
  hypothesis to test, not a measured crossover or proof of an optimal order.

## Pointers

- `/home/lexu/wse3-performance-model/demo/communication-algorithm/TODO.md`,
  scenario 4: pattern, comparison criteria and pending readiness/control checks.
- `/home/lexu/wse3-performance-model/docs/design/2026-09-12-layoutC-router-sweep-ordering.md`:
  candidate ordering analysis; full control/reset protocol remains unvalidated.
