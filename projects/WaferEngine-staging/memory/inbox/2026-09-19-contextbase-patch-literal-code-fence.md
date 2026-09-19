# ContextBase patch succeeds but metadata is still plain text — 2026-09-19

**Project:** WaferEngine-staging
**Author:** codex
**Status:** captured

## What happened / finding

- When converting an existing plain-text metadata paragraph into a fenced code block through ContextBase `update_document(editMode="patch")`, the API reported success but readback contained three backslash-escaped backticks followed by `text`, rather than a real code block. Observed on both PROGRESS and M1b milestone pages during the 2026-09-18 sync.
- The observed behavior is consistent with the replacement retaining paragraph/inline structure; the server's internal cause was not inspected. Do not assume a successful text patch also changes the rich-text block type.
- The verified repair was to retain the fetched page snapshot, remove only the exact malformed metadata paragraph with a patch, then prepend the intended fenced metadata using `editMode="prepend"`. Subsequent fetches began with an actual fenced `text` block. Parent/title, task counts, historical sections, and links remained intact.
- Readback also normalized harmless Markdown, including escaping `~` and splitting bold spans around inline code. A raw string mismatch is a review signal, not proof of content loss: distinguish formatting normalization from missing or mis-typed blocks.

## Implications / next actions

- After a write that changes block structure, inspect the fetched structure as well as text presence. For metadata, verify the opening code fence; for checklists, verify item identities and completion states, not only aggregate counts; retain middle/end sentinels on long pages.
- Keep a pre-edit snapshot and recheck for concurrent edits before a multi-call repair. Do not replace an entire rich document merely to repair one header. The two-call repair is not atomic; if interrupted, fetch before retrying.
- This is distinct from the previously captured partial-list sibling-drop hazard; it does not establish that arbitrary list patches are safe.
- **Promotion proposal:** add this block-type/readback guard to the existing `contextbase-maintenance` skill during reviewed maintenance. It is a cross-project procedure, not a new WaferEngine design fact. No skill was edited or installed by this reflect pass.

## Pointers

- Observed PROGRESS page: https://context.ed-aisys.com/doc/progressmd-9dEvXqtELH
- Observed milestone page: https://context.ed-aisys.com/doc/m1b-decode-continuous-batchingmd-v4oWcNPLvp
- Related existing capture: `memory/inbox/2026-07-24-meshagent-sync-outline-patch-list-drop.md`
- Session status already captured separately: `memory/inbox/2026-09-18-m1b-s1-handoff-and-tracking-ownership.md`
- Procedure destination, proposed only: `/home/lexu/claude-skills/contextbase-maintenance/SKILL.md`
