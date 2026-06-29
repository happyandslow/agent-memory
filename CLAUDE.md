# CLAUDE.md — Claude Code Instructions for Agent Memory

Follow `AGENTS.md` first. This file adds Claude Code-specific behavior for remote-server workflows.

## Session start

When Le starts a Claude Code session for a work project that uses this memory repo:

1. Identify the project slug.
2. Read `projects/<project>/memory/context.md`.
3. Read `projects/<project>/memory/project.md`.
4. Read relevant topic notes only.
5. Read `projects/<project>/tracking/status.md` and `projects/<project>/plan.md` if planning or status is needed.
6. Avoid loading unrelated project memory.

If the current work repo contains its own `AGENTS.md`/`CLAUDE.md`, obey that repo's instructions too. Treat the work repo as code source of truth and this memory repo as durable agent/human context.

## Dated-file convention

Before creating or linking durable memory artifacts, follow `AGENTS.md` dated-file rules. In particular, project `docs/` files must be named `YYYY-MM-DD-<slug>.<ext>`, and quick captures should go under `memory/inbox/YYYY-MM-DD-<short-topic>.md`. If you touch an undated non-exempt file, rename it and update references when the date is clear; otherwise record a manual conflict.

## End-of-session wrap-up

Before ending a meaningful session, update memory in this order:

1. `projects/<project>/memory/inbox/<YYYY-MM-DD>-<short-topic>.md` for quick capture if there is not time to curate.
2. Curate durable facts into `memory/context.md`, `memory/project.md`, and/or `memory/topics/*.md`.
3. Refresh `tracking/status.md` if the project state changed.
4. Append or refresh transcript/event pointers under `memory/transcripts/`.
5. Run `python3 scripts/check_memory_repo.py` from this repo.
6. Commit changes.

Suggested commit messages:

```text
memory(<project>): update current context
memory(<project>): record <topic> decision
status(<project>): refresh generated dashboard
```

## Claude Code hook guidance

On remote servers, prefer hooks that update **curated memory files** and commit this repo. Do not hook raw transcript dumps directly into git.

A typical remote setup has:

```text
~/repos/<work-project>/                 # actual code repo
~/repos/agent-memory/                   # this memory repo
```

A project-local `.claude/settings.local.json` may run scripts on `Stop`, `PreCompact`, or `SubagentStop` to write:

- `projects/<project>/tracking/status.md`
- `projects/<project>/memory/transcripts/index-<host>.md`
- `projects/<project>/memory/transcripts/events-<host>.jsonl`
- selected `memory/inbox/*.md` capture notes

Keep `.claude/settings.local.json` local and gitignored if it contains absolute paths.

## Raw transcript policy

Claude Code raw transcripts usually live under local `~/.claude/` paths. Do not copy them wholesale into this repo. If a raw excerpt is needed for audit/handoff, copy only the minimum relevant excerpt into a dated note and explain why.

## When uncertain

If you are unsure where to put information:

- short-lived or uncurated: `memory/inbox/`
- durable startup context: `memory/context.md`
- stable project facts: `memory/project.md`
- topic-specific knowledge: `memory/topics/<topic>.md`
- generated current status: `tracking/status.md`
- roadmap/progress narrative for Le: propose an edit to `plan.md`
