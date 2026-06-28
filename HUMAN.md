# HUMAN.md — How Le Should Use This Memory Repo

This is the human operating guide for work-project memory.

## What this repo is

`agent-memory` is the shared memory layer for work projects, especially projects developed on remote SSH servers with Claude Code. It is meant to make agents more stateless: a fresh Claude/Hermes session should quickly recover project context from curated files instead of relying on one long chat.

## Start a conversation with an agent

Use a short prompt like:

```text
Use the agent-memory repo. Project: <project-slug>.
Read only projects/<project-slug>/memory/context.md, memory/project.md, relevant topic notes, tracking/status.md, and plan.md. Then help me with: <task>.
```

For remote Claude Code sessions, start from the actual work repo and mention the memory repo path, for example:

```text
This work repo uses ~/repos/agent-memory/projects/<project-slug> as durable memory. Read its context/project/status files first, then work on <task>.
```

For Hermes on the Mac:

```text
Use /Users/lexu/Project/agent-memory/projects/<project-slug> as the project memory. Check current status and help me <task>.
```

## Wrap up a conversation

At the end of a meaningful session, ask the agent:

```text
Wrap up this session: update the project memory context/topic/status files, add any necessary transcript pointers, run the memory repo check, and commit the memory changes with a concise message.
```

If you do not want an automatic commit, say:

```text
Update memory but do not commit; show me the diff first.
```

## Human maintenance responsibilities

### Weekly for active projects

- Pull latest `agent-memory` locally.
- Check project `tracking/status.md` for accuracy.
- Review `memory/inbox/` and ask an agent to curate or delete stale notes.
- Make sure `memory/context.md` is still a useful session-start packet.
- Confirm no secrets or raw transcript dumps were accidentally committed.

### When starting a new project

1. Copy `projects/_template` to `projects/<project-slug>`.
2. Fill in `memory/project.md` with repo paths, remotes, machines, commands, and confidentiality notes.
3. Fill in `memory/context.md` with the minimal startup context.
4. Link the project into Obsidian under `10-work/<project-slug>`.
5. Add instructions in the actual work repo pointing to this memory location.
6. Configure Claude Code hooks if the project will be active on a remote server.

### When pausing a project

- Update `tracking/status.md` to say `Paused` or `Dormant`.
- Add clear restart instructions to `memory/context.md`.
- Make sure the latest branch/commit/paper/experiment pointers are in `memory/project.md` or a topic note.

### When resuming a project

- Read `index.md`, `memory/context.md`, `tracking/status.md`, and `plan.md`.
- Ask the agent to verify current external reality: git branch, open PRs/issues, experiment status, cluster/server state. Memory is context, not live proof.
- Update stale notes before doing major new work.

## What not to put here

Do not put these in `agent-memory`:

- passwords, API keys, private keys, access tokens;
- raw credential/config files;
- active databases;
- huge raw logs;
- full raw Claude/Hermes transcript dumps by default;
- personal/private notes unrelated to the work project.

## Suggested project lifecycle

```text
Start session → read compact memory → do work in actual repo/server → update curated memory → refresh status → commit memory → Hermes cron monitors freshness
```

The goal is not to record everything. The goal is to preserve the small amount of context that lets the next session restart quickly and correctly.
