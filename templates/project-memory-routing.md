## Project memory

This repo uses the shared `agent-memory` repository for durable project context.

Project slug: `<project-slug>`

Resolve the memory repo root on the current machine in this order:

1. If `$AGENT_MEMORY_ROOT` is set, use that.
2. Else if `../agent-memory` exists next to this work repo, use `../agent-memory`.
3. Else on Le's Mac, use `/Users/lexu/Projects/agent-memory`.

Then the project memory is:

```text
$AGENT_MEMORY_ROOT/projects/<project-slug>
```

Machine-specific known locations:

- Mac local memory repo: `/Users/lexu/Projects/agent-memory`
- Mac Obsidian view: `/Users/lexu/Library/CloudStorage/GoogleDrive-lxu5398@gmail.com/My Drive/Obsidian-note-vault/note-vault/10-work/<project-slug>`
- Remote/server memory repo: set `$AGENT_MEMORY_ROOT` or clone as a sibling `../agent-memory`

At session start, read from the resolved project memory path:

1. `memory/context.md`
2. `memory/project.md`
3. relevant files under `memory/topics/`
4. `tracking/status.md`
5. `plan.md` when planning or reporting status

At session wrap-up, update curated memory and commit changes in the memory repo.
Do not commit secrets, live databases, or bulk raw transcripts.
