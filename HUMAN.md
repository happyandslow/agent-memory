# HUMAN.md — How Le Should Use This Memory Repo

This is the human operating guide for work-project memory.

See AGENTS.md "## File model (v2 — 2026-07)" — the v2 source-vs-generated model and the
agent-memory skill supersede any older file-role descriptions below.

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
Use /Users/lexu/Projects/agent-memory/projects/<project-slug> as the project memory. Check current status and help me <task>.
```

## Wrap up a conversation

At the end of a meaningful session, ask the agent:

```text
Wrap up this session: write a dated memory/inbox capture per the write contract (do not
hand-edit context.md/status.md/timeline.md/index.md — those are generated), append to an
existing topic note only if clearly refining it in place, add any necessary transcript
pointers, run the memory repo check, and commit the memory changes with a concise message.
```

Deterministic regeneration of the generated views happens automatically via the Claude
Code Stop hook (per-turn, git-diff-gated, local commit only) or via the daily Hermes
maintain-pass cron. You do not need to ask for it explicitly, but you can force it:

```text
Run the agent-memory maintain pass on <project-slug> now.
```

If you do not want an automatic commit, say:

```text
Update memory but do not commit; show me the diff first.
```

## Dated-file convention

When you manually add docs, meeting notes, or TODO captures, include the date in the filename: `YYYY-MM-DD-<topic>.md`. For project `docs/`, use `docs/YYYY-MM-DD/YYYY-MM-DD-<topic>.<ext>` or a similarly dated path. Keep stable files like `plan.md` and `tracking/status.md` at their fixed names, but put dated notes/sections inside them when needed.

## Human maintenance responsibilities

### Weekly for active projects

- Pull latest `agent-memory` locally.
- Braindump into `capture.md` — this is your routine append-only surface; todos, meeting
  scraps, half-formed notes in any format. The maintain pass drains it for you.
- Check project `tracking/status.md` (generated) for accuracy against reality.
- Confirm `memory/inbox/` and `capture.md` are being drained by the maintain pass and not
  growing indefinitely; ask an agent to run `/agent-memory maintain <project>` if stale.
- Skim `memory/context.md` (generated) — it should still be a useful session-start
  packet; if not, that's a signal the maintain pass or `plan.md`/topics need attention,
  not a cue to hand-edit `context.md` itself.
- Confirm no secrets or raw transcript dumps were accidentally committed.

### When starting a new project

From `/Users/lexu/Projects/agent-memory`, run:

```bash
python3 scripts/init_project.py <project-slug> \
  --name "<Project Name>" \
  --code-repo "<git-url-or-path>" \
  --remote-path "<ssh-host:/path/to/work-repo>" \
  --link-obsidian
```

python3 scripts/init_project.py nc_service \
  --name "nc_service" \
  --code-repo "git@github.com:lausannel/nc_service.git" \
  --remote-path "gala2:/home/lexu/nc_service" \
  --link-obsidian

Example

```
cd /Users/lexu/Projects/agent-memory

python3 scripts/init_project.py llm-serving-paper \
  --name "LLM Serving Paper" \
  --code-repo "git@github.com:your-org/llm-serving-paper.git" \
  --remote-path "gpu-server:/home/lexu/repos/llm-serving-paper" \
  --link-obsidian

```

Then:

1. Fill in any remaining blanks in `projects/<project-slug>/memory/project.md` with repo paths, remotes, machines, commands, and confidentiality notes.
2. Add a first braindump entry to `projects/<project-slug>/capture.md` with the minimal
   startup context; run the `agent-memory` skill's `maintain` op (or Stop hook) to
   generate the first `memory/context.md` from it rather than hand-writing `context.md`.
3. Paste the printed portable routing snippet into the actual work repo's `AGENTS.md`, `CLAUDE.md`, and `HERMES.md`. The snippet should not contain only the Mac absolute path; it should let agents resolve `$AGENT_MEMORY_ROOT`, a sibling `../agent-memory` clone, or the Mac fallback path.
4. On remote machines such as `gala2`, clone this repo near the work repo, for example `~/repos/agent-memory`, or set `AGENT_MEMORY_ROOT` to its location.
5. Configure the Claude Code Stop hook (`templates/claude-stop-hook.md`) if the project will be active on a remote server.
6. Run `python3 scripts/check_memory_repo.py`, review the diff, commit, and push.

### When pausing a project

- Note the pause and restart instructions in `capture.md` (or `plan.md` if it's a durable
  decision) — do not hand-edit `tracking/status.md` or `memory/context.md` directly; run
  the maintain pass so it regenerates `Paused`/`Dormant` state and restart pointers from
  what you wrote.
- Make sure the latest branch/commit/paper/experiment pointers are in `memory/project.md` or a topic note.

### When resuming a project

- Read `index.md`, `memory/context.md`, `tracking/status.md`, and `plan.md` (all read-only
  starting points; the first three are generated).
- Ask the agent to verify current external reality: git branch, open PRs/issues, experiment status, cluster/server state. Memory is context, not live proof.
- Update stale notes via `capture.md`/topics/`plan.md` and rerun the maintain pass rather
  than patching the generated files.

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
Start session → read generated context/status → do work in actual repo/server → write a
dated capture (or braindump to capture.md) → Stop hook regenerates views locally →
Hermes cron runs the full maintain pass daily → Hermes cron monitors freshness
```

The goal is not to record everything. The goal is to preserve the small amount of context that lets the next session restart quickly and correctly.
