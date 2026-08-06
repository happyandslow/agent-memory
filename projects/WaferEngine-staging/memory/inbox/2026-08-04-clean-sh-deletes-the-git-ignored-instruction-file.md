---
date: 2026-08-04
project: WaferEngine-staging
tags: [tooling, gotcha, destructive, repo-hygiene]
---

# Freeing disk with the repo's own clean.sh also deletes CLAUDE.md — and git cannot restore it — 2026-08-04

**Project:** WaferEngine-staging
**Author:** claude
**Status:** drained   <!-- drained 2026-08-06 into memory/project.md Known pitfalls -->

## The situation this applies to

The sim-host disk is near full (observed 98% / 88 GB free on the shared `gala2` box, most of it
stale `out_*` build outputs), and you reach for the repo's own cleanup script — `./clean.sh`,
documented in `CLAUDE.md` as "clean all git-ignored build outputs (out_*/, staging, traces, logs),
keeping .claude/.vscode/.idea". That description reads as if it only removes regenerable artifacts.

## What happened / finding

- `./clean.sh -n` (dry run) lists **`CLAUDE.md`** and **`.superpowers/`** among "Would remove",
  alongside the expected `out_*/`, `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`.
- `CLAUDE.md` is **git-ignored by design** in this repo (its own Notes section says so: "CLAUDE.md
  and AGENTS.md are git-ignored — this guidance file is local, not committed"). So `git checkout`
  cannot bring it back; the only copies are the ContextBase / agent-memory mirrors, if current.
- The script's stated contract ("keeping .claude/.vscode/.idea") is true but incomplete — it keeps
  the `.claude` *directory* while removing the top-level instruction file.
- ⇒ Running `./clean.sh -y` to free space silently destroys the file that tells every future
  session how to work in this repo.

## Implications / next actions

- [ ] Always `./clean.sh -n` and read the **whole** list before `-y`. Never chain `-y` from a
      disk-pressure reflex.
- [ ] Prefer targeted deletion when the goal is just space:
      `rm -rf models/<model>/out_*` per model, after checking `ls -dlt` dates and that no other
      user's process is writing there (`gala2` is shared — check `pgrep -af cs_python` and whose
      paths they are before deleting anything large).
- [ ] Consider proposing a `clean.sh` fix so `CLAUDE.md` / `.superpowers/` are excluded — that is a
      repo change, not a memory item, so it needs Le's call.

## Pointers

- `clean.sh` at the repo root; described in `CLAUDE.md` § Common commands.
- Related: auto-memory note "Delete simfab traces after sim runs" — the same disk-pressure
  situation, but that one is safe to act on reflexively and this one is not.
- Context: 2026-08-04 M1-S2 checkpoint, freeing 79 GB of stale `out_*` (e2e + a `we-p2` worktree,
  all dated Jul 7–18).
