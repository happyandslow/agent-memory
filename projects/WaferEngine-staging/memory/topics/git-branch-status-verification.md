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
