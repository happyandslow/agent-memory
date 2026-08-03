---
summary: `editMode — "patch"` never matches on a mirrored page — findText is compared against Outline's *normalized* markdown, not your source file
tags: [contextbase, drained-inbox, 2026-07-30]
---

# `editMode: "patch"` never matches on a mirrored page — findText is compared against Outline's *normalized* markdown, not your source file

This topic was created by the 2026-08-03 maintain pass from a dated inbox capture. Keep it as the durable, topic-scoped home for the finding; the original capture is marked drained.

## Drained capture — 2026-07-30

Source: `memory/inbox/2026-07-30-patch-mode-cannot-match-mirrored-markdown.md`

# `editMode: "patch"` never matches on a mirrored page — findText is compared against Outline's *normalized* markdown, not your source file

Date: 2026-07-30 · ContextBase (Outline) via MCP, MeshAgent collection

**Project:** contextbase
**Author:** claude
**Status:** captured

## The situation this applies to

You are refreshing a durable-doc mirror that already exists (the `/meshagent-sync` flow), and
the file changed in only a handful of places. Re-uploading 40–80 KB verbatim looks wasteful,
and the sync playbook itself warns that a big `create`/`replace` can silently drop list
content — so `editMode: "patch"` looks like the obviously better tool: surgical, cheap, and
explicitly recommended by the MCP tool description as the safe way to edit an existing page.

You copy an exact line out of the source `.md`, pass it as `findText`, and get:

```
The specified text was not found in the document
```

…for text you can see in the file. Trying a shorter, more distinctive substring fails the same
way.

## Why

`findText` is matched against **the page's stored markdown**, which is Outline's re-serialized
form of what was imported — not the bytes you uploaded. The importer normalizes on the way in.
Observed in the same collection: `-` bullets come back as `*`; inline code spans that abut bold
markers get re-bracketed (`` `io_loc` `` inside a bolded phrase comes back as
`` `**io_loc**` ``); numeric text picks up escapes (`1.426` → `1\.426`). Any of these inside
your `findText` breaks the match, and the failure is indistinguishable from "the text isn't
there".

So **`patch` is only usable on text you wrote *through the API* and have not round-tripped**,
or on short fragments you have first read back with `fetch`. It is not usable for "apply my
git diff to the mirror".

## Implications / next actions

- For mirror refreshes there is no cheap path: it is header-`replace` + full `append` (the
  playbook's reliable route), at the cost of the whole file. Budget for that, or accept the
  mirror lagging and say so rather than half-updating it — the playbook's "never leave a mirror
  partially imported" rule bites here.
- If you do want `patch`, `fetch` the page first and copy `findText` **out of the fetched
  body**, not out of the source file.
- Sibling failure mode in the same importer:
  `2026-07-26-append-drops-checkboxes-nested-in-checkboxes.md`. Both are "the importer rewrites
  your markdown"; worth folding into one topic note about ContextBase import fidelity when this
  is drained.
- [ ] Consider noting in the `meshagent-sync` command that `patch` is not an option for the
      durable-doc mirror step, so nobody re-derives this.

## Pointers

- Attempted against `ROADMAP.md`'s mirror (`fa67902f-475f-4148-963d-a8062fbf7309`), MeshAgent
  collection `a2c5e79a-1d6f-4451-9e45-2501c5a5f6d4`, 2026-07-30.
- `/home/lexu/.claude/skills/meshagent-sync` (the command whose Step 1 this affects).
