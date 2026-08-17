# M3.5 symmetric refactor — a completed Claude review PASS exists, conflicting with the "no Claude verdict" line — 2026-08-16

**Project:** WaferEngine
**Author:** claude
**Status:** drained 2026-08-17 into `memory/topics/meshjit-code-relocation.md`; unresolved applicability recorded in `tracking/conflicts.md`

## What happened / finding

- Situation: you are reading
  `inbox/2026-08-16-waferllm-function-container-m35-resident-helper-fork.md`,
  which says "Claude Code attempts ended with execution errors and produced no
  verdict; do not cite a Claude PASS for this replacement" — and you are about
  to either dismiss the M3.5 result as un-reviewed by Claude or re-run the
  review from scratch.
- In fact a completed independent Claude read-only review of the replacement
  artifact exists: session `72054b9f` (transcript mtime 2026-08-16 17:58 UTC),
  target `/home/lexu/WaferEngine-staging/.m35_symmetric_refactor`. Verdict:
  **PASS** on all eight requested invariants — four-way symmetry from one
  frozen `A_both` source; entry offsets 196/0 cross-checked against linked ELF
  symbols; resident call target = `m35_vecmat_computation` at 0x3f00 (not the
  callback at 0x3fc0); ABI retained at 0x3e00 (5×u16); paired receiver buffer
  literals correctly +8 B (5736/5768/5800 vs 5744/5776/5808), not cross-wired;
  no shadow vecmat in the in_page receiver; actual/normalized complete-image
  accounting not double-counting slot bytes; claims Grade-E/no-runtime only.
  Two non-blocking findings (language precision / check strength), no
  correctness defects.
- The reviewed numbers match the codex note exactly (ABI 0x3e00, slot
  0x4100=16640, offsets 196/0, vecmat 0x3f00/188 B, callback 0x3fc0/8 B), so it
  is the same replacement design. [unverified] whether the staging copy
  `.m35_symmetric_refactor` was byte-identical to the WaferLLM `m35/` tree at
  review time.
- Timeline: an earlier same-day Claude attempt (`a7776bf0`, 17:53 UTC) ended
  with no verdict — likely what the codex note refers to. The codex note was
  written at 18:17, *after* the 72054b9f PASS completed, so the "no Claude
  verdict" claim was already stale when written; the author presumably could
  not see the Claude transcript.
- Do not auto-resolve which statement wins: the maintain pass should reconcile
  the two (verify the staging copy vs the WaferLLM tree, then update the M3.5
  note or record the PASS as scoped to the staging copy).

## Implications / next actions

- [ ] Maintain pass: reconcile with
  `inbox/2026-08-16-waferllm-function-container-m35-resident-helper-fork.md`
  (its "do not cite a Claude PASS" line) before either statement is promoted
  into a topic.

## Pointers

- `/home/lexu/.claude/projects/-home-lexu-WaferEngine-staging/72054b9f-4bfb-4677-81c2-f308f07f2e0c.jsonl` (the PASS review)
- `/home/lexu/.claude/projects/-home-lexu-WaferEngine-staging/a7776bf0-63cd-46bc-be04-beb9659a60c7.jsonl` (the no-verdict attempt)
- `/home/lexu/WaferEngine-staging/.m35_symmetric_refactor` (reviewed artifact)
- `projects/WaferEngine/memory/inbox/2026-08-16-waferllm-function-container-m35-resident-helper-fork.md`
