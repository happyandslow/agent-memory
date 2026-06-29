# ContextBase Project Memory

## Identity

- Project slug: `contextbase`
- Human name: ContextBase
- Owner: Le Xu
- Area: `10-work/contextbase`
- Confidentiality/access boundary: work/research-group knowledge base; access-control design is security-sensitive.

## Source of truth

- Code repo: `/Users/lexu/Project/contextbase` per the 2026-06-29 design note; verify current path before use.
- Remote server path(s):
- Local checkout path(s): `/Users/lexu/Project/contextbase` (verify)
- Obsidian path: `/Users/lexu/Library/CloudStorage/GoogleDrive-lxu5398@gmail.com/My Drive/Obsidian-note-vault/note-vault/10-work/contextbase`
- Memory repo path: `/Users/lexu/Projects/agent-memory/projects/contextbase` on Mac; `~/agent-memory/projects/contextbase` on gala2.

## Machines and agents

| Host | Role | Paths | Notes |
| --- | --- | --- | --- |
| gala2 | remote memory maintenance | `~/agent-memory/projects/contextbase` | Current conflict-resolution/check target. |
| MacBook | Obsidian/Hermes/local view | `/Users/lexu/Projects/agent-memory/projects/contextbase` | Local path should be verified/synced. |

## Commands

### Build/test/check

```bash
# In agent-memory
python3 scripts/check_memory_repo.py
```

### Status update

```bash
# Update tracking/status.md after auditing live repo/deployment state.
```

## Conventions

- Follow root AGENTS.md dated-file convention for docs and inbox captures.
- Put durable design notes under `docs/YYYY-MM-DD/YYYY-MM-DD-<topic>.md` or an equivalent dated docs path.

## Known pitfalls

- Memory note paths may mention `/Users/lexu/Project/contextbase`; verify whether the actual Mac path is `/Users/lexu/Project` or `/Users/lexu/Projects` before editing code.
- Do not treat access-control memory as proof of live deployment state; inspect the current deployment/config first.

## Important links

- `docs/2026-06-29-restricted-sharing-acl-design.md` — restricted-sharing/default-deny realm ACL design.
