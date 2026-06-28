# HERMES.md — Hermes Instructions for Agent Memory

Follow `AGENTS.md` first. This file describes how Hermes should use and maintain this memory repository.

## Role

Hermes is primarily the local orchestrator/backstop for this repo:

- pull the memory repo;
- inspect diffs and freshness;
- summarize recent memory changes to Le;
- alert when a project has stale memory or failing hooks;
- help create project scaffolds and Obsidian links;
- avoid becoming the only persistence path for remote work.

Remote Claude Code hooks should write memory at source. Hermes cron should verify and summarize.

## Default local paths

Memory repo:

```text
/Users/lexu/Project/agent-memory
```

Obsidian vault:

```text
/Users/lexu/Library/CloudStorage/GoogleDrive-lxu5398@gmail.com/My Drive/Obsidian-note-vault/note-vault
```

Expected Obsidian work project location:

```text
<obsidian-vault>/10-work/<project>
```

## Starting work with Hermes

When Le asks about a work project:

1. Locate the project under `projects/<project>`.
2. Read `memory/context.md` and `memory/project.md`.
3. Read relevant topic notes only.
4. Check `tracking/status.md` and git status if the task is about freshness/current state.
5. Use live source tools when the question is about current external state; memory is context, not proof of current reality.

## Hermes cron pattern

Recommended recurring jobs:

1. `git pull --ff-only` in `/Users/lexu/Project/agent-memory`.
2. Run `python3 scripts/check_memory_repo.py`.
3. Report:
   - projects with missing required files;
   - projects whose memory/status files are stale;
   - recent commits since last report;
   - uncommitted local changes.
4. Optionally summarize recent changes into a short Discord message.

Cron should not silently overwrite human-authored `plan.md`.

## Freshness expectations

Use these as defaults unless a project overrides them in `memory/project.md`:

- active project: `memory/context.md` or `tracking/status.md` should change at least weekly;
- dormant project: stale is acceptable if `tracking/status.md` says dormant/paused;
- `memory/inbox/` should be curated periodically, not allowed to grow indefinitely.

## Safety

Do not commit or sync secrets. Do not move files into another Hermes profile. Do not edit active work repos unless Le asks. For generated Obsidian files, regenerate rather than manually patching large repeated status blocks when possible.
