---
summary: A content-fact verifier passed the compressed doc — but every unchecked subtask lost its checkbox — 2026-08-01
tags: [WaferEngine-staging, drained-inbox, 2026-08-01]
---

# A content-fact verifier passed the compressed doc — but every unchecked subtask lost its checkbox — 2026-08-01

This topic was created by the 2026-08-03 maintain pass from a dated inbox capture. Keep it as the durable, topic-scoped home for the finding; the original capture is marked drained.

## Drained capture — 2026-08-01

Source: `memory/inbox/2026-08-01-compression-subagent-drops-tracking-checkboxes.md`

---
date: 2026-08-01
project: WaferEngine-staging
tags: [methodology, docs, subagent, compression, verification, procedural]
---

# A content-fact verifier passed the compressed doc — but every unchecked subtask lost its checkbox — 2026-08-01

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured

## The situation this applies to

A milestone/tracking doc has grown bloated (here `M2-tiering-cost-model.md` 1064 lines,
`M3-idle-pe-tier.md` 961 lines) and you dispatch a subagent to compress it. To do this
safely you wrote a "must-survive facts" checker — 51 / 62 literal payload facts grepped
before and after — and it reports **ALL PRESENT**. You conclude the compression was lossless.

It was not. Later you notice the `- [ ]` **checkboxes for every un-done subtask**
(S2b/S3a/S3b/S3c/S4/S5/S7) are gone — only the `[x]` done ones survived. The subtasks' prose
is intact, so the fact checker never flagged it, but **subtasks with no checkbox are
untrackable**, and this project's rule is that checkbox-granular state lives only in the
milestone file.

## Why the verifier missed it

A content/fact-diff checks that *claims* survive. **Trackable state — checkboxes, status
markers, `⬜`/`🟡`/`✅` cells — is not a "fact" in that set**, so its loss is invisible to a
grep-the-numbers verifier. Compression subagents optimize prose density and treat an empty
checkbox as noise.

⇒ When compressing a tracking doc, add the **structural inventory** to the survival check,
not just the facts: count `- [ ]` + `- [x]` before/after and require the totals to match;
same for status glyphs and table rows. Or tell the subagent explicitly, verbatim, that
checkboxes are load-bearing and must be preserved 1:1.

## A related doc-integrity trap in the same session

The "authoritative" copy is not always the populated one. `milestones/M2-experiment-
register.md` (git, self-declared authoritative) and its agent-memory mirror were both
**0-byte**; the actual content lived only in the ContextBase mirror — the sync direction had
been inverted. **A file labelled "source of truth" can be empty while the "mirror" holds
everything.** Check byte counts, not labels, before trusting which copy is canonical.

## Implications / next actions

- [ ] **Promotion candidate — procedural, not a fact about this project.** It is a method
      for a class of situations ("verifying a lossy transform preserved what mattered"), and
      it generalizes any time a subagent rewrites a structured doc. Pairs with the existing
      negative-control / test-the-instrument-on-a-known-pair notes.

## Pointers

- `scripts/verify_m2.sh` / `verify_m3.sh` (the fact-only checkers that passed); backups
  `scratchpad/M2-backup-1647.md`, `M3-backup-*.md`.
- Same session also caught a stale plan cursor: PROGRESS + `M2-tiering-cost-model.md` header
  still said "S3 next, blocked on workload" after E9/E10/E10D had already closed old S3 — the
  register (which supersedes the S<n> tracker) is authoritative for status.
