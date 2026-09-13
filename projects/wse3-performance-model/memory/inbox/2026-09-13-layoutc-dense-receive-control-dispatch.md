# Dense payload arrives but its completion marker never runs — 2026-09-13

**Project:** wse3-performance-model
**Author:** codex
**Status:** captured

When moving LayoutC feedback from a u32 data-task prototype to asynchronous
dense BF16 receives on the same IQ as control markers, completing the counted
receive is not sufficient to release a deliberately blocked task dispatcher.
The working endpoint blocks IQ0 while two half-frame DSDs own it, then explicitly
unblocks IQ0 so ROW_DONE/STREAM_END control tasks can run. An `on_control` handler
on the counted receive rejects a premature marker as truncation; an unexpected
data task rejects extra payload. Neither case may acknowledge a ready frame.

This endpoint was verified on CS-3 in a full 128-column, five-layer group and
in two-epoch north/south microtests. Dropped and duplicated fragments produced
error7/error6 and prevented the next epoch; temporary diagnostic probes were
kept only in the reproduction archive. This is procedural knowledge potentially
useful to the communication-pattern skill, not a claim about arbitrary control
encodings or all SDK versions (tested SDK 2.10.0, WSE-3).

- [Receive ownership and explicit unblock](/home/lexu/wse3-performance-model/demo/qwen3-4b-thinner-stage/layoutC/code/src/group_link.csl:63)
- [Measured evidence, limitations, and disposable probes](/home/lexu/wse3-performance-model/docs/reports/2026-09-13-layoutC-first-group-feedback.md)

The terminal-in-final-row design is now tested for the first group; the earlier
stacked-group collision note remains relevant to whole-model integration.
