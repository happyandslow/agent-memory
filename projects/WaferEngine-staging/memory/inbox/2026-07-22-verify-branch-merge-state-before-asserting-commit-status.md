# A durable doc's "code uncommitted / in progress" can be stale — verify commit/merge state on the branch before restating it — 2026-07-22

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured

## The situation this applies to

You are reconciling or reporting a subtask's status, and a durable doc
(`PROGRESS.md`, `milestones/M{n}-*.md`) says something like **"S6x code
uncommitted, pending Le's review/merge"** or **"IN PROGRESS / handed to a new
session."** You are about to restate that, or write it into another doc, or plan
around it. **Do not trust the prose.** In this repo the durable docs are updated
by whichever session is active, and a *later* session can advance everything
around a subtask while carrying its stale status line forward verbatim — so the
doc can lag reality by days and by a whole "committed + merged" step.

## The finding (this happened this session, user caught it)

I wrote "S6a-prefill code uncommitted on `lexu/staging/s6a-inner-pe-kv-route-a`,
pending review/merge" into PROGRESS + the milestone + agent-memory + ContextBase —
**inferred from a stale doc line, without checking git.** The user pointed at the
branch model. Ground truth was the opposite: the S6a-prefill code was already
committed as `e0a19fc` (touches `prefill.csl`/`ht_head.csl`/`launch.py`/
`kv_store.py`/`comm_pe.csl`) and **merged into the feature branch
`lexu/staging/kv-feature` via PR #1 (`0db3fc2`)** — done, verified, landed. The
stale "IN PROGRESS" line came from the S6b session, which advanced its own work
but never folded the prefill device-verification back in.

## The check that would have prevented it (do this before writing any commit/merge claim)

```bash
git rev-parse --abbrev-ref HEAD                        # what am I actually on
git branch --merged lexu/staging/kv-feature            # what has landed on the feature branch
git merge-base --is-ancestor <branch> lexu/staging/kv-feature && echo MERGED || echo NOT
git show -s --format='%ci  %s' <sha>                   # date + subject of the commit
git show --stat <sha> -- models/<kernel>/              # what files it actually touched
git diff --stat lexu/staging/kv-feature -- <files>     # is my working tree == the merged code?
```

If the diff is empty, the working tree carries the merged code; the subtask is
landed regardless of what a doc's prose says.

## Branch model (Le's convention, stated this session — the backdrop)

- **`lexu/staging/kv-feature` is the main feature branch; per-milestone branches
  (`s6a-inner-pe-kv-route-a`, `s6b-force-decode`, …) converge onto it.** `main` =
  `fcfc8c1`. Merges land via PRs (S6a = PR #1, `e0a19fc` → `0db3fc2`).
- A branch cut *after* a merge carries that merged code: `s6b-force-decode` was
  cut from post-merge `kv-feature`, so its tree already contains all of S6a — which
  is why the S6a-prefill code is present and byte-identical there.

## Implications / next actions

- [ ] **Procedural — promotion candidate.** This is the same class of error as
  `cerebras-debugging` L1 ("Identify the artifact before you theorize about it"):
  extend it to **identify the branch/merge state before asserting commit status.**
  Consider a one-line addition to the `cerebras-debugging` ledger / laws rather
  than a new topic.

## Pointers

- Fixed in: `PROGRESS.md § S6a`, `milestones/M0-reuse-foundation.md § S6a`,
  agent-memory `plan.md` (commit `29b16ae`), ContextBase PROGRESS mirror + Project
  Overview + the 2026-07-21 session log.
- Related: `memory/inbox/2026-07-23-host-kv-code-placement-convention.md` (where
  the host code lives in the tree — a different axis from the branch model here).
