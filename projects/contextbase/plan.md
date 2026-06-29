# ContextBase Plan

Human-maintained roadmap and durable progress narrative.

Agents may propose edits, but should not overwrite this mechanically. Generated/current status belongs in `tracking/status.md`.

## Goals

- Make ContextBase (self-hosted Outline) private/default-deny by project realm.
- Preserve a practical short-term configuration path while keeping the long-term fork/enforcement roadmap explicit.

## Milestones

- [ ] Stage 0 — audit existing collection exposure and public shares.
- [ ] Stage 1 — configure current Outline features: disable public sharing, make collections private, model realms as groups.
- [ ] Stage 2 — enforce private-by-default collection creation in the fork.
- [ ] Stage 3 — add/clarify a realm layer over Outline group ACLs.
- [ ] Stage 4 — implement request-access flow if needed.

## Decisions

| Date | Decision | Rationale | Link |
| --- | --- | --- | --- |
| 2026-06-29 | Use collection-level realm ACLs as the main path; keep cross-cutting label/IFC as research only. | Outline already implements collection-level group/user ACL union semantics; the immediate gap is defaults, enforcement, and UX. | `docs/2026-06-29-restricted-sharing-acl-design.md` |

## Narrative progress log

### 2026-06-29

- Added restricted-sharing ACL design note: `docs/2026-06-29-restricted-sharing-acl-design.md`.
