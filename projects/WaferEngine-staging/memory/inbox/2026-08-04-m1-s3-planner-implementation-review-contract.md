# M1-S3 planner/implementation/review contract — 2026-08-04

**Project:** WaferEngine-staging
**Author:** hermes
**Status:** drained   <!-- drained 2026-08-06 into plan.md Decisions + Next actions -->

## What happened / finding

- When an M1-S3 step has been agreed with Le, Codex remains the planner and reviewer; it must not implement the production change itself.
- Codex sends the approved, bounded task to Claude Code using `claude-fable-5` with automatic fallback to `claude-opus-4-8`. Claude Code implements and runs the agreed gates; Codex then independently reviews evidence and diff, returns concrete findings, and repeats the implement/review cycle until the gate passes.
- A user phrase such as “do S3.1 first” selects the next planned step; it does not silently replace this implementation-role contract.
- `launch.py` modularisation is a separate pure-move task with a bit-identical gate. It must be discussed and approved before dispatch and must not be mixed with the next S3 behaviour change.
- Every step boundary is a hard approval gate. Before R0a, R0b, each review-driven correction pass, and every later S3.x implementation, Codex states the exact task and evidence gate, stops, and waits for Le's explicit approval before invoking Claude Code.

## Implications / next actions

- [ ] Agree the standalone `launch.py` modularisation boundary with Le before dispatching any further S3 implementation.
- [ ] For each later S3 step, preserve the sequence: agree plan → Claude Code implement/test → Codex review → Claude Code iterate → Codex accept.

## Pointers

- `/home/lexu/.codex/attachments/ab0705c2-d526-44dc-a7c7-fedbe9447702/pasted-text.txt`
- `GOALS.md` launch.py modularisation entry
- `milestones/M1-intra-pe-reuse.md` § S3
