# WSE-3 Performance Model Project Memory

## Identity

- Project slug: `wse3-performance-model`
- Human name: `WSE-3 Performance Model`
- Owner: Le Xu
- Area: `10-work/wse3-performance-model`
- Confidentiality/access boundary: Shared private work-project memory; do not
  store secrets, credentials, or raw private transcripts.

## Source of truth

- Code repo: `/home/lexu/wse3-performance-model` (project directory; not a Git
  repository as of 2026-08-27)
- Remote server path(s): gala2:/home/lexu/wse3-performance-model
- Local checkout path(s): /home/lexu/wse3-performance-model
- Obsidian path: `/Users/lexu/Library/CloudStorage/GoogleDrive-lxu5398@gmail.com/My Drive/Obsidian-note-vault/note-vault/10-work/wse3-performance-model`
- Memory repo path: gala2
  `/home/lexu/agent-memory/projects/wse3-performance-model`; Mac
  `/Users/lexu/Projects/agent-memory/projects/wse3-performance-model`

## Machines and agents

| Host | Role | Paths | Notes |
| --- | --- | --- | --- |
| gala2 | primary development | `/home/lexu/wse3-performance-model` | WSE-3 performance-model workspace |
| MacBook | Obsidian/Hermes/local view | `/Users/lexu/Projects/agent-memory/projects/wse3-performance-model` | Link into `10-work/wse3-performance-model` when the memory repo is synced locally. |
| Mac mini | backup |  |  |

## Commands

### Build/test/check

```bash
# No build or validation command exists yet; add commands with the first implementation/model.
```

### Status update

```bash
cd /home/lexu/agent-memory
python3 /home/lexu/.codex/skills/agent-memory/scripts/check_memory_repo.py --root /home/lexu/agent-memory
```

## Conventions

- Evidence chain: implementation -> measurement -> analysis -> model -> validation.
- Raw measurements are immutable; corrections create a new run or dated erratum.
- Separate measured, fitted, assumed, and predicted quantities explicitly.
- Every derived result names its source measurement IDs and analysis code.

## Known pitfalls

- The workspace is not yet a Git repository; do not assume revision metadata is
  available until version control is deliberately initialized.
- No measured results or calibrated models existed at project creation.

## Important links

- Work directory: `/home/lexu/wse3-performance-model`
- Project memory: `/home/lexu/agent-memory/projects/wse3-performance-model`
