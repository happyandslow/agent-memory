# `git merge-base --is-ancestor <orig-sha> <branch>` returns false after a SQUASH-merge though the content is fully present — verify feature-on-branch by content — 2026-07-24

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured

## The situation this applies to

You want to answer "is feature X (a milestone branch, a PR's work) merged into
`lexu/staging/kv-feature` yet?" — to decide a branch base, or to write a
commit/merge status line into a durable doc. You reach for the ancestor check the
prior capture recommends:

```bash
git merge-base --is-ancestor <feature-tip-sha> lexu/staging/kv-feature && echo MERGED || echo NOT
```

It prints **NOT** — and you are about to conclude the feature is not on the
branch. **This conclusion is wrong when the team squash-merges.** In this repo PRs
land as squash-merges (PR #1 `0db3fc2`, PR #2 `ad52da0` "S6b force decode (#2)"),
so the merge commit has a *new* SHA and the original feature-tip SHA is **not an
ancestor of it** — even though the merge commit contains all of the feature's
content. The ancestor check tests commit lineage, not content presence; a squash
severs the lineage while preserving the content.

## The finding (happened this session, in the M1 planning session)

Checking whether S6b (force-decode) was on `kv-feature` before cutting the M1
branch, I ran `git merge-base --is-ancestor 8a7cd98 lexu/staging/kv-feature` →
**NO**, and wrote into the first draft of `milestones/M1-intra-pe-reuse.md` that
"S6b is only on `s6b-force-decode`, NOT on `kv-feature`" and proposed merging it
first. The user corrected: S6b **was** already merged, via **squash** PR #2
`ad52da0`. The lineage check lied because of the squash; the content was fully
present. This is the *same* verification the 2026-07-22 capture recommends — so
that capture's method is incomplete, and the prior capture existing did **not**
stop me from the trap.

## The check that is actually reliable (verify by CONTENT, not by original SHA)

```bash
# 1. content probe — a symbol the feature introduces:
git grep -c forced_decode_len lexu/staging/kv-feature -- 'models/qwen3_1p7b-decode/src/*.csl'
# 2. or a file-level diff of the feature's touched files vs the branch — empty == present:
git diff --stat lexu/staging/kv-feature <feature-branch> -- <the feature's files>
# 3. the squash commit itself is usually named after the PR:
git log --oneline -8 lexu/staging/kv-feature      # look for "… (#2)" squash subjects
```

If the content probe hits / the diff is empty, the feature is on the branch —
regardless of what `--is-ancestor` on the original tip SHA says.

## Implications / next actions

- [ ] **Procedural — promotion candidate, and it AMENDS an existing lesson.**
  This refines `2026-07-22-verify-branch-merge-state-before-asserting-commit-status.md`:
  that capture recommends `git merge-base --is-ancestor <branch> …` as *the*
  reliable check (its line 35), but under a squash-merge convention that check
  produces false negatives. The reliable primitive is **verify by content**
  (`git grep` / file diff, its line 38), not the ancestor-SHA test. Fold this
  caveat in when the branch-state lesson is promoted (candidate home: the
  `cerebras-debugging` "identify the artifact before you theorize" ledger, or
  wherever the 07-22 branch-state lesson lands). Statable without the specific
  commits, so it passes the altitude test.

## Pointers

- Recorded in: `milestones/M1-intra-pe-reuse.md` § "Branch base (resolved 2026-07-24)"
  (the gotcha note); PROGRESS.md 2026-07-24 session log; agent-memory
  `topics/kv-cache-policy-tradeoffs.md` (2026-07-24 update, git-tooling bullet).
- Amends: `memory/inbox/2026-07-22-verify-branch-merge-state-before-asserting-commit-status.md`.
- Squash merges this session: PR #1 `0db3fc2` (S6a), PR #2 `ad52da0` (S6b) onto `lexu/staging/kv-feature`.
