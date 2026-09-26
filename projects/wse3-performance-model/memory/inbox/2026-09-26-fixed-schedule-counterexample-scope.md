# Scope of fixed-schedule counterexamples — 2026-09-26

**Project:** wse3-performance-model
**Author:** codex
**Status:** captured

## What happened / finding

When using scheduler counterexamples to justify new protocol machinery, separate
an invalid work order from asynchronous overlap and from hypothetical topology.

- Le explicitly corrected the three-request/four-lane AR example: selecting the
  next token before the returning work that generates its input is a schedule
  error, not a defect inherent in asynchronous overlap. A bound on active lanes
  for one round-robin policy is not a universal bound on physical buffer capacity.
- Source-verified: current single-block layer0 input is copied from local
  group_input; it is not a second fabric sender competing on the feedback IQ.
  Feedback is broadcast across each A1 row (WEST to RAMP plus EAST), so multiple
  PEs do receive replicas of that row shard. Neither observation establishes
  the proposed two-source split-credit deadlock in the current implementation.
- Analytical scope: that split-credit example additionally assumes a shared
  receive domain, independently conflicting source grants, and senders requiring
  all target credits. Reordered-frame misidentification similarly assumes sender
  order changes while the receiver retains its old mapping. These counterexamples
  do not establish that a mutually consistent fixed-order design needs dynamic
  compute arbitration or explicit identity headers; implicit edge order may suffice.

## Implications / next actions

Recheck these premises before carrying the 2026-09-25 proposed header/grant
machinery into implementation. This is a source/user-correction capture, not a
new hardware failure, performance result or approved replacement protocol.
No project design/tracking document was edited during this read-only clarification.

## Pointers

Source root: /home/lexu/wse3-performance-model/demo/fused-block/xz-staircase/package/
- tall/src/tall_stage.csl:220-223 — local layer0 input copy.
- tall/host/group_routing.py:90-105 — row broadcast and ACK routes.
- tall/src/group_link.csl:68-85,104-110 — receive-slot inference and row credit.
- /home/lexu/wse3-performance-model/docs/reports/2026-09-25-cohort-free-scheduler-review.md
  — distinguish the R1 dynamic draft from the later fixed-selection design.
