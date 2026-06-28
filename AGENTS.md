# AGENTS.md — Agent Memory Operating Instructions

This repository is Le Xu's private durable memory layer for work projects. It is designed for remote-first projects where development happens on SSH servers, while Obsidian on the Mac provides a local reading/planning interface under `10-work/<project>`.

## Prime directive

Maintain **curated, compact, project-scoped memory**. Do not dump raw transcripts or noisy logs. Make future fresh agent sessions easier by preserving decisions, current state, repo paths, commands, pitfalls, and next steps in predictable files.

## Default context loading

When working in this repo or in a work project that points here:

1. Read this file.
2. Read the project-specific `projects/<project>/memory/context.md`.
3. Read `projects/<project>/memory/project.md`.
4. Read only relevant topic notes under `projects/<project>/memory/topics/`.
5. Read `projects/<project>/tracking/status.md` for generated current state.
6. Read `projects/<project>/plan.md` for human-maintained roadmap/progress narrative.

Do **not** scan all projects or all transcript indexes unless the user asks for archaeology or cross-project context.

## File ownership rules

- `projects/<project>/plan.md`: human-maintained roadmap and durable progress narrative. Agents may propose edits, but should avoid overwriting it mechanically.
- `projects/<project>/tracking/status.md`: generated dashboard/current-state summary. Safe for deterministic scripts/hooks to overwrite.
- `projects/<project>/memory/context.md`: compact session-start packet. Keep short and high-signal.
- `projects/<project>/memory/project.md`: stable project facts, repo paths, conventions, known remotes, commands.
- `projects/<project>/memory/topics/*.md`: topic-specific context packets.
- `projects/<project>/memory/inbox/`: temporary capture area. Periodically curate into context/topic/project files and clear/archive.
- `projects/<project>/memory/transcripts/`: indexes/events/pointers. Do not store bulk raw transcripts by default.
- `projects/<project>/memory/agents/`: machine/agent-specific setup notes.

## What to commit

Commit:

- durable decisions and rationale;
- current work state and next actions;
- repo paths, branches, build/test commands;
- experiment summaries and result pointers;
- meeting/handoff notes;
- compact transcript indexes and event records;
- generated `tracking/status.md` snapshots when useful.

Do not commit:

- secrets, tokens, passwords, SSH keys;
- raw credential files;
- active SQLite/database files;
- full raw Claude/Hermes transcript stores by default;
- dependency directories or caches;
- large logs unless explicitly requested and justified.

## Update discipline

At the end of meaningful work on a project:

1. Update `memory/context.md` if the next session needs different startup context.
2. Update or create a relevant `memory/topics/*.md` if topic-specific knowledge changed.
3. Update `memory/project.md` if stable paths/conventions/tools changed.
4. Update `tracking/status.md` manually or via script.
5. If there were important events, append a pointer/index entry under `memory/transcripts/`.
6. Commit with a concise message, e.g. `memory(project-x): update eval status and next steps`.

## Obsidian integration

The local Obsidian vault should expose each project under:

```text
/Users/lexu/Library/CloudStorage/GoogleDrive-lxu5398@gmail.com/My Drive/Obsidian-note-vault/note-vault/10-work/<project>
```

This may be a symlink, worktree, submodule checkout, or mirrored copy from `projects/<project>`.

## Conflict handling

If git conflicts occur, preserve user-authored `plan.md` content first, then reconcile generated files. For generated `tracking/status.md`, regeneration is usually preferable to manual conflict surgery.

## Security/confidentiality

Assume work-project memory may contain sensitive research context. Keep this repository private. If a project has a stricter access boundary than the rest, move it to a separate memory repo.
