# Source/target switch markers and sentinel reset — 2026-09-12

**Project:** wse3-performance-model
**Author:** codex
**Status:** captured

## Finding

When one strip stream crosses several source switches before reaching target
switches, control commands need explicit pop sites; consuming a command does
not consume the whole control wavelet.

- A validated isolated recipe uses `[ADV]` for source grants and `[NOP,ADV]`
  for target advance. Normal source junctions use pop_on_advance; the final
  source junction uses always_pop to strip the NOP before the target zone.
  Pair completion sends ROW_DONE, then target advance, then the next grant.
- A final STREAM_END sentinel is insufficient as an all-receiver write fence.
  A control-only reset sweep checks exact receive counts plus ROW_DONE at each
  receiver, restores switches, and permits the next frame only after completion.
- Evidence: real CS-3 and SDK 2.10 WSE-3 simulator; 3x7 active PEs, four sources
  of 16 u32 values, two destination rows with two replica columns, two distinct
  epochs in each direction. Both positive cases passed exact equality; omitting
  one ROW_DONE still delivered all first-frame data and STREAM_END but blocked
  restart. No floating-point or performance claim.

## Boundary

This is an isolated communication proof. Its memcpy IQ/OQ2/3/4 and control
entrypoint 40 cannot be copied into tall, whose collectives use IQ/OQ3..7 and
main uses local slot 8. Full queue/task integration, packed f16, larger fanout,
and multi-layer feedback remain gates. The source buffers/compute kernels were
not instrumented. This is a procedural candidate for later curation, not an
installed skill or a full-group acceptance result.

## Pointer

[Protocol, source archive and raw evidence](/home/lexu/wse3-performance-model/docs/reports/2026-09-12-layoutc-marker-reset-verification.md).
