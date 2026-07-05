# HERMES.md — Hermes Instructions for Agent Memory

Follow `AGENTS.md` first. This file describes how Hermes should use and maintain this memory repository.

See AGENTS.md "## File model (v2 — 2026-07)" — the v2 source-vs-generated model and the
agent-memory skill supersede any older file-role descriptions below.

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
/Users/lexu/Projects/agent-memory
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

## Dated-file convention

Hermes maintenance must enforce the `AGENTS.md` dated-file convention: non-exempt project `docs/` artifacts require `YYYY-MM-DD-<slug>.<ext>` filenames, inbox captures require dated filenames, and ambiguous dates should be reported as manual conflicts rather than guessed.

## Hermes cron pattern

The daily cron **is** the full agent-driven maintain pass. The procedure lives in one
place: `<claude-skills>/agent-memory/PLAYBOOK.md`. Read it and follow it — do not keep a
separate inline description of the maintenance logic here or in the
`synced-project-memory-vault` skill; both should delegate to `PLAYBOOK.md` so an edit
there (via `git pull`) changes behavior everywhere.

Recommended recurring jobs:

1. `git pull --ff-only` in `/Users/lexu/Projects/agent-memory`.
2. Run the `agent-memory` skill's `maintain` operation (drain `capture.md` + dated
   `inbox/` into `plan.md`/`topics/`/decisions; scan `meetings/` read-only; regenerate
   `context.md`/`status.md`/`index.md`/`timeline.md`; declutter; flag ambiguous items to
   `tracking/conflicts.md`; commit safe mechanical changes).
3. Run `python3 scripts/check_memory_repo.py` as a deterministic pre-flight/sanity check.
4. Report:
   - projects with missing required files;
   - projects whose memory/status files are stale;
   - recent commits since last report;
   - uncommitted local changes;
   - any new entries in `tracking/conflicts.md`.
5. Optionally summarize recent changes into a short Discord message.

Cron auto-commits mechanical curation (drain, regenerate, dedupe, rename, prune) but
never auto-resolves ambiguous human conflicts, and never silently overwrites
human-authored `plan.md` or `capture.md`.

## Freshness expectations

Use these as defaults unless a project overrides them in `memory/project.md`:

- active project: `memory/context.md` or `tracking/status.md` (both generated) should
  change at least weekly;
- dormant project: stale is acceptable if `tracking/status.md` says dormant/paused;
- `capture.md` and `memory/inbox/` should be drained by the maintain pass regularly, not
  allowed to grow indefinitely un-curated.

## Safety

Do not commit or sync secrets. Do not move files into another Hermes profile. Do not edit
active work repos unless Le asks. Never hand-edit generated views (`memory/context.md`,
`tracking/status.md`, `memory/timeline.md`, `index.md`); always regenerate them via the
skill instead of patching repeated status blocks by hand.
