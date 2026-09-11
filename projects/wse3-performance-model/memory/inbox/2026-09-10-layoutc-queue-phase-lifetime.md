# Layout C: queued next-step input survives the output phase — 2026-09-10

**Project:** wse3-performance-model
**Author:** codex
**Status:** captured

When a pipelined edge relay reuses a compute queue, finishing the current
payload and flushing its output queue does not establish that the input queue
is empty: upstream may already have sent the next step's payload.

In the unequal-height Layout C probe, restoring IQ3 from vertical C12 to
compute C0 immediately after Z[t] triggered the simulator's "router is holding
wavelets" error. The final schedule keeps the vertical binding from Z[t]
through X[t+1], then restores computation only after X is count-drained.
The synchronous compute Y collective preserves the X-to-Z phase boundary;
an identity probe must retain that dependency. A 33-step probe with changing
column/step payloads passed exact QKV/X/output checks; independent QKV and X
mapping faults were rejected. This is simulator evidence, not hardware proof.

Evidence and exact scope:
`/home/lexu/wse3-performance-model/docs/reports/2026-09-10-layoutC-unequal-datapath.md`.
Implementation:
`/home/lexu/wse3-performance-model/demo/qwen3-4b-thinner-stage/layoutC/code/src/tall_stage.csl:192`.
