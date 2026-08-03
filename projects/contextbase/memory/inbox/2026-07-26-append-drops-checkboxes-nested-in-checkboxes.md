# A mirrored page is missing whole sub-items after import: `update_document` drops `- [ ]` items nested inside another `- [ ]` item

Date: 2026-07-26 · ContextBase (Outline) via MCP, MeshAgent collection

**Project:** contextbase
**Author:** claude
**Status:** drained

## The situation this applies to

You are mirroring a markdown file into ContextBase (the `/meshagent-sync` durable-doc mirror,
or any large-file import). The write reports success. You fetch the page back and the
top-level structure is all there — but **specific nested items are simply gone**, with no
error and no placeholder. Verifying only the file's *last* line will not catch it; the loss
is in the middle.

## What actually drops

Two distinct behaviours, only the second is data loss:

1. **Known and already documented in the sync protocol:** a single large `create`/`replace`
   can silently drop plain `-` / `1.` list content. The protocol's workaround is
   header-then-`append`, because the append path preserves those.
2. **New this session:** even on the `append` path, a `- [ ]` **checkbox item nested inside
   another `- [ ]` checkbox item** is dropped. Observed on a milestone file whose `S6`
   subtask had nested `(i)/(ii)/(iii)` findings and nested `S6a`/`S6b` checkbox children —
   all children vanished while `S6` itself survived.

Attempting to repair it with `editMode: "patch"` **made it worse** — two further sibling
items (`S4`, `S5`) disappeared. Recovery required replacing the page back to its header and
re-appending in **six smaller chunks**, with the nested checkbox children **flattened to top
level**. All content then survived; only the visual nesting differs from the source file.

## Working rules for mirroring

- Never nest a `- [ ]` inside another `- [ ]` in text you append. Flatten one level (prefix
  the child, e.g. `- [ ] S6a · …`) — the mirror is for reading, the git file stays canonical.
- Prefer **several small appends** over one large one; split at clean section boundaries,
  never inside a table or a fenced block.
- Do not reach for `patch` to repair a partial import. Replace back to the header and
  re-append.
- Verify with **two** sentinels, not one: the file's last non-empty line **and** a mid-file
  bullet or table row. A late-line-only check passes happily through a hole in the middle.
- Harmless cosmetic artifacts seen alongside this (not loss, do not chase): a `5b.` list item
  folding into the preceding paragraph, and a `+ …` fragment rendering as a sub-bullet.

## Confidence

Observed directly while syncing a 550-line milestone file; the flattened re-append was
verified by re-fetch. Not isolated to a minimal repro — the exact trigger is inferred from
the shape of what disappeared (nested checkbox children), not from a controlled test.

## Implications

- [ ] Fold into the `/meshagent-sync` protocol text, which currently warns only about
      large `create`/`replace` and plain lists — the nested-checkbox case and the
      two-sentinel verification rule are not in it yet.

## Pointers

- MeshAgent collection mirror pages under *Durable Docs (git mirror) › Milestones*.
- Source repo `/home/lexu/WaferEngine-staging`, `milestones/M0-reuse-foundation.md`.
