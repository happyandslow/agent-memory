# Resuming Layout C: preserve the prior height baseline — 2026-09-10

**Project:** wse3-performance-model
**Author:** codex
**Status:** captured

## What happened / finding

- When resuming full-model Layout C planning, do not infer the final stage heights from the 8/16/8 test miniature. Le directed A1 to shrink and A3 to grow within their shared 128x256 half. The original author derived A1/A2/A3 heights 80/256/160; Le agreed to record that analysis on September 9 and explicitly recalled the height discussion on September 10. Preserve those numbers as the next trial baseline, not as separately user-approved or verified final dimensions.
- Width remains 128 for all three stages; A2 retains full height for KV. The 16 spare rows are real unused rows, not hidden-dimension padding. The old capacity evidence used matching per-PE dimensions in a 128-row scaffold, not the true target geometry. New full-dimensional linked-memory and routing validation remain necessary.

## Pointers

- Decision evidence and corrected allocation: `/home/lexu/wse3-performance-model/docs/design/2026-09-10-layoutC-full-allocation.md`, “Recovered decision and capacity evidence”.
- Original Claude session `824688b0-1bbe-4637-99c5-03ed21f26380`, user correction at JSONL line 4364 and agreement at line 4372.
