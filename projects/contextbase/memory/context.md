# ContextBase Context

Compact startup packet for fresh agent sessions. Keep this short enough that an agent can read it every time.

## What this project is

- ContextBase is Le's self-hosted Outline-based knowledge base for ED-AISYS/research group context.
- Current focus is access control: make project collections default-deny and scoped by project/person realms rather than visible to the whole workspace.

## Current state

- A draft design note exists at `docs/2026-06-29-restricted-sharing-acl-design.md`.
- The note concludes the short-term path is mostly configuration of existing Outline features, while the long-term path is thin enforcement + realm UX in the fork.

## Current focus

- Audit current collection exposure and public sharing.
- Decide operational defaults for realm group permissions and who may create collections/realms.

## Next likely actions

- [ ] Run Stage 0 audit from the design note against the live ContextBase/Outline deployment.
- [ ] Decide whether realm members should default to `read` or `read_write`.
- [ ] Decide whether existing public shares should be revoked immediately or grandfathered.
- [ ] If implementing, inspect the actual ContextBase repo before editing; memory is context, not live proof.

## Must-read topic notes

- `docs/2026-06-29-restricted-sharing-acl-design.md` — restricted-sharing/default-deny realm ACL design and staged roadmap.

## Important constraints

- Treat access-control changes as security-sensitive; do not silently widen access.
- Preserve default-deny/manual-review behavior when facts are ambiguous.
- Do not store secrets or live deployment credentials in agent-memory.

## Restart checklist

1. Verify live ContextBase repo/deployment state; memory may be stale.
2. Read `tracking/status.md`.
3. Read `docs/2026-06-29-restricted-sharing-acl-design.md`.
4. Proceed with the user's task.
