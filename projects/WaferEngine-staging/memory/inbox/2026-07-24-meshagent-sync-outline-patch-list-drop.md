---
name: meshagent-sync-outline-patch-list-drop
description: ContextBase/Outline patch-mode edits silently drop sibling list items; re-mirror via header-replace+append, and list Logs before creating a session log.
metadata:
  type: feedback
---

# meshagent-sync: Outline `patch` on a list region silently drops sibling bullets — and check for a parallel session's work before writing

**Project:** WaferEngine-staging (but the lesson is workflow-level, not project-specific)
**Author:** claude
**Status:** captured
**Promotion:** procedural + cross-project → **candidate for the `meshagent-sync` skill** (add the two guards below). Not a WaferEngine fact.

## Situation

Running `/meshagent-sync` (or the sync step of `/checkpoint`) to mirror the durable docs
(GOALS/PROGRESS/milestones) and write a session log into the ContextBase MeshAgent
collection, via `mcp__contextbase__update_document` / `create_document`. Two ways this
lost or duplicated work in one session — both silent.

## Hazard 1 — `editMode:"patch"` on a Markdown **list** region silently drops the sibling list items

To insert one new `§7` bullet into the GOALS mirror I used `update_document editMode:"patch"`
with `findText` = the adjacent bullet. The patch applied — but Outline's importer **dropped
almost every OTHER bullet in that `§7` list** (12 bullets → 2). The doc came back structurally
gutted, no error. This is the same "large edit silently drops plain `-`/`1.` list content on
import" failure the sync protocol already warns about for `create`/`replace` — it bites `patch`
too when the matched region is (or is adjacent to) a bulleted list.

**What works instead:** to update a mirror, **re-mirror it fully** — `update_document
editMode:"replace"` with the header only, then `editMode:"append"` the file's verbatim body
(split into a couple of appends for a long file). The append path preserves list content.
Reserve `patch` for **prose-only, non-list** spans (e.g. one sentence inside a paragraph — the
Project Overview "Current status" bullet patched fine because the replacement was inline prose,
no new list structure). **Never `patch` a bulleted section.** After any mirror write, the
protocol's verify step (fetch + confirm a late-file sentinel AND a mid-file bullet) is what
catches this — do not skip it.

## Hazard 2 — a parallel session may have already synced; check before you write, or you duplicate

A different session had already done most of this checkpoint's ContextBase work (updated
Project Overview, created two dated session logs) without my knowing. I created a **third,
overlapping** session log for the same day and had to delete it. Also several in-repo durable
docs were already updated by that session, so my edits were gap-fills, not the bulk.

**Guards:** before creating a session-log page, `list_collection_documents` on the collection
and scan Logs for an existing same-day entry. Before re-mirroring a durable doc, check its
`updatedAt` (via `fetch`) — a recent timestamp from another session usually means it is already
current and only a small delta (if any) is yours to add. Treat the in-repo durable docs the same
way: `grep` the target section first; a parallel session may have already written it.

## Why it matters

Hazard 1 is **data loss** (a whole backlog section vanished, recoverable only because I had the
verbatim source in git and re-mirrored). Hazard 2 is wasted work + clutter. Both are invisible
without the explicit verify/list checks. Git is the source of truth for the mirrors, so a
damaged mirror is always recoverable by re-mirroring from the repo file — but only if you notice.

## Pointers

- Skill: `meshagent-sync` (the two guards belong in its protocol, next to the existing
  "header-then-append, lists drop on big create/replace" note).
- Same-conversation instances: GOALS §7 patch-drop + repair; duplicate 2026-07-23 session log
  created then deleted (`8c3d2c76`).
