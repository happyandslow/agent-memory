# M1b-S1 independent completion target — 2026-09-18

**Project:** wse3-performance-model (session workspace; implementation belongs to WaferEngine-staging)
**Author:** codex
**Status:** captured

## What happened / finding

- When scoping WaferEngine-staging M1b-S1 from this workspace, Le explicitly clarified that the eventual deliverable includes implementation and tests, not only a design document. A short request must be able to complete on EOS while peers continue, whether or not a new request fills the vacated capacity.
- The immediate requested step is a source-grounded audit of existing versus desired EOS behavior and a per-file high-level change list, including treatment of frozen metadata and whether completed lanes should skip computation or be removed from the batch.

## Implications / next actions

- Treat independent request completion as a requirement separate from replacement/admission. Specific control encoding, compute masking, batch compaction, and host notification proposals have not been approved by this clarification. No implementation or device validation was performed in the audit.

## Pointers

- Authority: Le's explicit requirement clarification in the 2026-09-18 conversation; not an inferred implementation decision.
- `/home/lexu/WaferEngine-staging/docs/session-prompts/M1b-S1.md`
- `/home/lexu/WaferEngine-staging/milestones/M1b-decode-continuous-batching.md`
- Audited local source HEAD: `2371b583a727055aae9042a26ee12d3037c0d4c5`; verify live state before implementation.
