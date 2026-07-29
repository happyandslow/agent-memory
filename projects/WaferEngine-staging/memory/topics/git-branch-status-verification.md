---
summary: Git branch/merge status verification guardrails for WaferEngine-staging: durable docs can carry stale commit-state prose, and squash merges make original-tip ancestry checks false-negative; verify feature presence by live branch state plus content probes/diffs before writing status claims.
tags: [waferengine-staging, git, branch-state, squash-merge, verification, workflow]
---

# Git branch / merge status verification guardrails

Use this note before writing any durable claim that a milestone branch, PR, or feature is "uncommitted", "pending merge", "not on `kv-feature`", or "landed".

## Core rule

Durable prose is context, not proof. Verify live git state and content presence before restating commit/merge status.

In this repo, stale status lines have survived in `PROGRESS.md`, milestone docs, and derived memory notes after later sessions advanced code and merged PRs. Separately, feature PRs may land as squash merges, so the original feature-tip SHA is not necessarily an ancestor of the target branch even when the feature content is present.

## Checks that prevent stale-status mistakes

```bash
git rev-parse --abbrev-ref HEAD
git log --oneline -8 lexu/staging/kv-feature

git branch --merged lexu/staging/kv-feature
# Useful for non-squash lineage only; not sufficient after squash merges:
git merge-base --is-ancestor <feature-tip-sha> lexu/staging/kv-feature && echo MERGED || echo NOT

# Reliable after squash: probe content, not only original SHA lineage.
git grep -c <feature-symbol> lexu/staging/kv-feature -- '<relevant paths>'
git diff --stat lexu/staging/kv-feature <feature-branch> -- <feature-touched-files>
```

Interpretation:

- Empty file-level diff or positive feature-symbol probe means the feature content is present on the branch, even if the original feature-tip SHA is not an ancestor.
- `merge-base --is-ancestor <original-tip> <target>` answers a lineage question; after a squash merge it can return false while content is fully landed.
- A branch cut after a merge carries that merged code. Check the branch base/topology before assuming a subtask is still isolated on its old milestone branch.

## Someone links you a branch and you plan measurements against its committed results

A branch is a **snapshot with a date**, and the numbers committed inside it age with the code.
Before quoting a branch's recorded result files, establish where its tip sits on the upstream line.

```bash
# Recovers the fetch line that CREATED a local branch: remote URL, remote ref, fast-forward or not.
git reflog show <branch>

# Settles staleness in one command.
git merge-base --is-ancestor <maybe-older> <maybe-newer> && echo ANCESTOR || echo NOT
```

`git reflog show` is the diagnostic that turns "I think this ref tracks that upstream branch" into a
confirmed identity rather than an inference — it is how the `pr14-real` / `pr14-head` map in
[[pr14-real-serving-port-contract]] was established. Two limits to state explicitly rather than
imply: a **local branch cannot tell you whether the remote has moved since the fetch** (re-fetch, do
not assume currency), and when two refs track the same upstream line, write the branch map down
(ref → remote → tip → date) where the next session reads it, not in chat.

When a linked branch does turn out to be stale, separate **what moved from what didn't** — that is
what tells you which conclusions survive. In the 2026-07-28 case the 5-commit gap left the *device*
anchors stable within ~1% while every *host-side* overhead changed by multiples, so device-derived
conclusions survived the stale baseline and host-derived ones did not. Baselining the stale ref would
have measured two already-fixed implementation artifacts and charged them to the architecture.

## A merge that reports zero conflicts is evidence about text, not about meaning

A three-way merge reconciles **lines**. It cannot reconcile a **contract that lives in more than one
file** — a symbol name and its call sites, a wavelet count and its reader, a struct width and its
consumers. The files that merge *cleanly* are where the breakage hides, because both sides touched
different lines of the same contract.

So after resolving any protocol change, **verify the contract end-to-end rather than verifying that
the merge succeeded**: sweep for symbols the other side renamed that our call sites still reference
(that class never shows as a conflict), and assert that a sender's emitted width still equals its
receiver's expected width. Worked examples of both breaks, from the PR #14 trial merge, are in
[[pr14-real-serving-port-contract]] § 2026-07-28. This is a different failure from the stale-status
and squash-merge problems above: those are about *what landed*, this is about *whether what landed
still means the same thing*.

## Incidents captured

- 2026-07-22: S6a prefill was incorrectly described as uncommitted/pending review from stale durable prose. Ground truth: S6a was committed as `e0a19fc` and squash/PR-merged into `lexu/staging/kv-feature` as PR #1 (`0db3fc2`).
- 2026-07-24: S6b force-decode was initially misclassified as not on `kv-feature` because `git merge-base --is-ancestor 8a7cd98 lexu/staging/kv-feature` returned false. Ground truth: S6b was present through squash PR #2 (`ad52da0`), and content verification was the reliable check.

## Writing rule for future agents

Before updating `plan.md`, project docs, ContextBase mirrors, or status summaries with commit/merge state:

1. Identify the target branch and feature branch/PR.
2. Check recent target-branch log for squash PR subjects.
3. Verify by content probe or file diff for the feature's touched files.
4. State both the branch and evidence when the status matters.

## Last updated

2026-07-25 — drained 2026-07-22 and 2026-07-24 inbox captures into this topic; explicit squash-merge caveat added.
