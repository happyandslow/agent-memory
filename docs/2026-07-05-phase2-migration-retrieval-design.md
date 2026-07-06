# Agent-Memory Phase 2 — Checker Consolidation, Migration & Retrieval Design Spec

Date: 2026-07-05
Owner: Le Xu
Status: Approved design; implementation planning next.
Depends on: Phase 1 (`2026-07-05-agent-memory-skill-phase1-plan.md`, merged/installed).

## Problem

Phase 1 built and installed the `agent-memory` skill (write contract + curate + generated
views) on Mac, gala2, and Hermes. Three gaps remain before the system is fully realized:

1. **Two colliding checkers.** The repo's v1 `scripts/check_memory_repo.py` requires four
   scaffold READMEs per project (and doesn't skip `_template`); the skill's checker is
   richer but separate. The declutter step wants to prune the very dirs v1 mandates, so
   the first real prune would fail the mandated check.
2. **The 4 real projects are still un-migrated** — triplicated `context.md`/`status.md`/
   `index.md`, no `capture.md`, no `timeline.md`, vestigial empty scaffold dirs.
3. **No retrieval side.** Agents and the human can only read whole files; there is no
   managed index to look information up by topic/keyword, defeating the original
   context-efficiency goal ("hierarchy + index so we don't load everything").

Two findings from live data shaped this design:
- The deterministic dup-detector finds **zero verbatim** cross-file duplication; the real
  triplication is paraphrased, so dedup is an **agent-judgment task**, not scriptable.
- `find_conflicts` currently false-flags `meetings/` and `memory/inbox/` (intentional
  dirs) as empty scaffold.

## Goals

- One checker, with a relaxed v2 structural rule; no same-name collision.
- All 4 projects migrated to the v2 single-source model, each in its own revertable commit.
- A managed, auto-generated retrieval layer: topic summaries/tags → per-project + repo
  catalogs → a keyword `ask` query returning `file:line` pointers, no embeddings.

## Non-goals

- Semantic/embedding search (stdlib only; keyword scoring is sufficient).
- gala2 install (done in Phase 1 follow-up).
- Migrating ContextBase content (external store; single pointer only).

## Design

### Part A — Mechanical prerequisites (TDD)

**A1. Consolidate to one checker.**
- Extend the skill's `check_memory_repo.py` with a relaxed v2 per-project structural check:
  require only `plan.md`, `capture.md`, `memory/project.md`. Scaffold dirs and generated
  views are optional. Skip `_template`. Keep the existing secret + dated-docs checks.
- Replace the repo's `scripts/check_memory_repo.py` with a thin wrapper that execs the
  skill's checker with `--root <repo>` (resolve the skill dir via the same order as
  `memory_lib.resolve_root`), so every existing `python3 scripts/check_memory_repo.py`
  call (cron, CLAUDE.md, HUMAN.md) keeps working unchanged.
- **This is the blocker — it must land before any prune.**

**A2. `find_conflicts` fixes.**
- Exclude `meetings/` and `memory/inbox/` from empty-scaffold detection (intentional dirs).
- Add un-drained-inbox detection: flag `memory/inbox/*.md` whose front-matter `Status:` is
  not `drained`, and `capture.md` containing content beyond the template stub.

**A3. Retrieval layer.**
- **Topic frontmatter:** the `topics/<slug>.md` template gains `summary:` (one line) and
  `tags:` (list) in a YAML front-matter block. Existing bodies unchanged.
- **Catalog generation** (extend `build_views.py`):
  - Per project: emit a generated topic-catalog section into `index.md` — a table of
    *topic → summary → tags → path*, read from each topic's front-matter (fallback: first
    body line if no summary yet).
  - Repo-level: generate `projects/CATALOG.md` (GENERATED header) — every project × its
    topics × one-liners × current status line. One file answers cross-project "where is X?".
- **`ask.py`** (new script): `python3 ask.py "<query>" [--project SLUG] --root <root>` →
  deterministic ranked results. Scoring: keyword/tag match over `CATALOG.md` +
  topic front-matter + topic bodies + `timeline.md`; return top-N `path:line` pointers with
  a one-line snippet each. Stdlib only (`re`, scoring). Exit 0 always; prints "no matches"
  when empty.
- **Skill wiring:** add an `ask` mode to `SKILL.md` (`/agent-memory ask "<q>" [project]`)
  and a short "Query / lookup" section to `PLAYBOOK.md` pointing at `ask.py`.

**A4. Minor final-review cleanups.**
- `install.sh`: guard the Claude branch so that if `~/.claude/skills/agent-memory` exists
  as a real directory (not a symlink), it errors clearly instead of nesting a symlink inside.
- Drop the moot `--now`/write-flag global constraint from the plan template: `build_views`
  is a write tool by design and `timeline.md` is filename-date based, not clock based.

### Part B — Migration (agent-driven, auto-commit per project)

The 4 real projects: WaferEngine, WaferEngine-staging, contextbase, nc_service. For each,
via the skill's maintain pass (`/agent-memory maintain <project>`):

1. Scaffold `capture.md` if missing (from `_template`).
2. Ensure the GENERATED header on `context.md`, `tracking/status.md`, `index.md`.
3. **Drain (agent judgment):** make `plan.md` the canonical home for goals / milestones /
   decisions / next-actions; rewrite `context.md` and `status.md` as thin projections with
   the duplicated prose removed. Preserve all substantive content — distill, don't discard.
4. **Populate retrieval:** add `summary:` + `tags:` front-matter to each existing topic note.
5. Generate `timeline.md`, `index.md` (+ its catalog section) via `build_views.py`.
6. **Prune** vestigial empty dirs: remove README-only/empty `memory/transcripts/`,
   `memory/agents/`, and `memory/topics/` only if the project truly has no topics. **Keep**
   `meetings/` and `memory/inbox/` even when empty.
7. Ambiguities / contradictions → `tracking/conflicts.md`; never auto-resolve.
8. **One commit per project** (auto-committed), so any single project is trivially revertable.

After all four: generate the repo-level `projects/CATALOG.md`.

### Safety model

Auto-commit per project (as chosen), but **not auto-push**:
- Sync-first (`git pull --ff-only`) before starting; run on the Mac.
- One commit per project → per-project `git revert` is trivial.
- **Hold the push** until the human has reviewed `git log` + diffs across all four projects
  plus `CATALOG.md`; then push once.
- The consolidated checker must PASS after each project's commit.

## Sequencing

1. **Part A** as a TDD subagent-driven plan (A1 first — the blocker — then A2, A3, A4).
2. Verify the consolidated checker PASSes on the current repo.
3. **Part B** project-by-project; review the 4 commits + catalog; push once.

## Success criteria

- `python3 scripts/check_memory_repo.py` (repo wrapper) and the skill checker are the same
  logic; PASS on all projects with only `plan.md`/`capture.md`/`project.md` required.
- No project has hand-authored duplication across `context.md`/`status.md`/`index.md`.
- Every topic note has `summary` + `tags`; `index.md` shows a topic catalog;
  `projects/CATALOG.md` lists all projects × topics.
- `/agent-memory ask "<keyword>"` returns correct `file:line` pointers into the right topics.
- `meetings/` and `inbox/` survive pruning; `transcripts/`/`agents/` (if empty) are gone.

## Out of scope / deferred

- Embedding/semantic retrieval.
- Any further Hermes cron changes (already delegates to PLAYBOOK).
- Remaining cosmetic carried-minors that don't affect behavior.
