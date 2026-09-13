# Budget LayoutC transport with retained external components — 2026-09-13

**Project:** wse3-performance-model
**Author:** codex
**Status:** captured

When selecting apparently unused colors from the standalone tall launcher,
include the components needed to restore the complete 4B model. Le explicitly
reaffirmed that K-pipe belongs in the new layout and that existing external
components must be reassessed. The objective remains full-model on-chip
execution; the complete-group correctness gate still precedes integration
and end-to-end performance tests.

Source-verified constraint: C16 serves A2 X-row multicast in tall, but retained
legacy K-pipe uses C16/C17 for pipe 7. Both colors transit non-owner strip PEs,
and owner PEs configure NORTH-to-RAMP / RAMP-to-SOUTH. Therefore a feedback
route through the same strip cannot claim C16 is spatially disjoint merely
because A1/A3 do not use it. No new hardware result is claimed.

The old strip selects pipe = local_y % 8. Directly attaching A3 rows with
16 hidden elements to A1 rows with 32 elements splits each required pair
(2r, 2r+1) across pipes. Ownership/count analysis confirms that assigning both
halves to r % 8 instead would balance 20 source shards and 10 destination
shards per pipe (320 elements each). This is a candidate mapping only;
forward counts, orientation, queues, route lifecycle and STOP/rearm still
require implementation and validation. Retain K-pipe in the component budget;
do not assume its old equal-height transport can be copied unchanged.

## Evidence pointers

- [K-pipe ownership and C16/C17 binding](/home/lexu/wse3-performance-model/demo/qwen3-4b-thinner-stage/layoutC/code/src/decode_strip_pe.csl:61).
- [Transit routes on every active strip](/home/lexu/wse3-performance-model/demo/qwen3-4b-thinner-stage/layoutC/code/launch.py:1939).
- [Forward lengths and receiver ownership](/home/lexu/wse3-performance-model/demo/qwen3-4b-thinner-stage/layoutC/code/src/decode_strip.csl:146).
- [Full-model construction gates](/home/lexu/wse3-performance-model/docs/design/2026-09-10-layoutC-full-allocation.md:174).

Observed working-tree sources on 2026-09-13; repository HEAD
38ac5b7a7d999689fe472c766e233fe545502c95 does not track the demo files.
