# Meetings

Shared working area for meeting slides and materials (pptx, pdf, keynote, images, notes).

## Naming and layout

- Put each meeting deck directly in this directory as `YYYY-MM-DD.pptx`, using the
  meeting date.
- Keep regenerable material for that deck in `YYYY-MM-DD-src/`: `deck.json`, figure
  scripts, `figures/`, and rendered `preview/` files.
- Treat the root-level dated PPTX as the presentation artifact. Do not create topic-named
  deck directories alongside it.

Legacy files that predate this convention may keep their existing names. This folder
remains exempt from the repository's strict dated-memory-file checker.

**Co-edited by you and agents.** Agents may create, append to, or modify slides here when
you ask; you also edit on top of them. Guardrails:

- Treat each deck as one working file; version it through git commits, not copies.
- Avoid two parties editing the same deck at the same time. Before editing, an agent
  should pull latest and commit promptly after; if unsure whether you have unsaved local
  edits, it should ask rather than overwrite.
- The maintenance pass never reorganizes this folder on its own. It only reads slides to
  distill decisions/TODOs into `capture.md` / `plan.md` / `timeline.md`.
