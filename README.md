# Agent Memory

Private work-project memory repository for remote-first agent workflows.

This repo is the durable transport/audit layer between:

```text
remote work repo + Claude Code hooks
→ curated project memory committed here
→ local Obsidian vault under 10-work/<project>
→ Hermes cron monitors freshness, summarizes, and alerts
```

Use this repository for **curated memory only**: compact context packets, topic notes, status dashboards, session indexes, and handoff notes. Do **not** commit secrets, raw credential files, live databases, or bulk raw transcripts.

## Layout

```text
agent-memory/
  AGENTS.md                 # instructions for all coding/agent assistants
  CLAUDE.md                 # Claude Code-specific operating instructions
  HERMES.md                 # Hermes-specific operating instructions
  HUMAN.md                  # Le's human workflow and maintenance responsibilities
  projects/
    _template/              # copy this for each new work project
    <project>/
      index.md              # landing page for Obsidian
      plan.md               # human-maintained roadmap/progress narrative
      tracking/status.md    # generated current dashboard; safe to overwrite
      memory/
        README.md
        project.md          # durable facts, repo paths, conventions
        context.md          # compact start packet for fresh agent sessions
        topics/             # topic-scoped context packets
        transcripts/        # indexes/events/pointers, not raw transcript dumps
        inbox/              # temporary notes before curation
        agents/             # per-host/per-agent setup notes
  templates/                # reusable project files
  scripts/                  # validation/maintenance utilities
```

## Add a new work project

Preferred command:

```bash
python3 scripts/init_project.py <project-slug> \
  --name "<Project Name>" \
  --code-repo "<git-url-or-path>" \
  --remote-path "<ssh-host:/path/to/work-repo>" \
  --link-obsidian
```

This copies `projects/_template` to `projects/<project-slug>`, fills common placeholders, optionally creates the Obsidian `10-work/<project-slug>` symlink, and prints a **portable** memory-routing snippet to paste into the actual work repo's `AGENTS.md`, `CLAUDE.md`, and `HERMES.md`.

The routing snippet should not hard-code only the Mac path. In remote-first repos it should tell agents to resolve the memory repo root in this order:

1. `$AGENT_MEMORY_ROOT` if set on the current machine;
2. `../agent-memory` if the memory repo is cloned as a sibling of the work repo;
3. `/Users/lexu/Projects/agent-memory` as the Mac fallback.

Then project memory is always `$AGENT_MEMORY_ROOT/projects/<project-slug>`.

Manual equivalent:

1. Copy `projects/_template` to `projects/<project-slug>`.
2. Fill in `projects/<project-slug>/memory/project.md` and `memory/context.md`.
3. Link or expose that folder in Obsidian under:

   ```text
   /Users/lexu/Library/CloudStorage/GoogleDrive-lxu5398@gmail.com/My Drive/Obsidian-note-vault/note-vault/10-work/<project-slug>
   ```

4. In the actual work repo, add/update `AGENTS.md`, `CLAUDE.md`, and `HERMES.md` to point agents to this memory path.
5. On remote servers, configure Claude Code hooks to update curated memory here and commit it.
6. Configure Hermes cron locally to pull this repo and report stale or changed memory.

## Dated-file convention

All project `docs/` files must use `YYYY-MM-DD-<slug>.<ext>` filenames, even when they also live under a `docs/YYYY-MM-DD/` directory. Quick captures belong in dated `memory/inbox/YYYY-MM-DD-<topic>.md` files. Stable control files such as `index.md`, `plan.md`, `tracking/status.md`, `memory/context.md`, and `memory/project.md` keep their predictable names but should record dated updates inside the file when facts are time-sensitive. Agents should fix undated non-exempt files during maintenance, or mark a manual conflict if the correct date is unclear.

## Policy

- Curated memory is source of truth; local agent transcript stores are cache/audit only.
- Default session context should be `memory/context.md` plus relevant `memory/topics/*.md`, not the whole repository.
- `plan.md` is human-maintained. Do not overwrite it from scripts.
- `tracking/status.md` is generated/current-state and may be overwritten by deterministic scripts.
- `memory/transcripts/` stores indexes and event pointers only unless Le explicitly requests raw excerpt archival.
- Keep project-specific confidentiality boundaries in mind. If a project needs different access control, use a separate private memory repo instead of this shared repo.
