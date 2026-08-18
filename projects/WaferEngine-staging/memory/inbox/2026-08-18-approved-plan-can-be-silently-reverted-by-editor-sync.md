---
date: 2026-08-18
project: WaferEngine-staging
tags: [workflow, plan-mode, codex-review, gotcha, verification]
---

# The plan file on disk may not be the plan that was approved — 2026-08-18

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured

## The situation this applies to

You have iterated a plan file (e.g. `~/.claude/plans/<name>.md`) through several
review rounds — in this case five Codex rounds ending in APPROVE — while Le was
co-editing the same file from an external editor whose buffer syncs/writes back
to disk. You are about to start implementing "the approved plan".

Symptom that announces the problem: the Read tool's cached view and the disk
content disagree (Read reports "unchanged" while injected reminders show older
text), or sections you know were rewritten reappear in their pre-review form.

## What happened / finding

- After Codex round-5 APPROVE of plan v5 (E13 decode-KV-egress), the on-disk
  file had silently reverted to the **rejected v3**: an external editor buffer
  holding the older version was saved over the reviewed file. No error, no
  conflict marker — the approval had simply been detached from the bytes on
  disk.
- Implementing what was on disk would have re-introduced defects Codex had
  explicitly killed (silent count-exact deadlock, non-deterministic Gate 3).
- What caught it: **before implementing, grep the disk directly for
  discriminator strings** — a few strings that exist *only* in the approved
  version (here `TOP_K=1`, `dbg_force_eos_step`, `free-run greedy`) and a few
  that exist *only* in the rejected one (`aligned PRNG`, `force/bounded-step`).
  Approved-markers = 0 hits and rejected-markers > 0 was the unambiguous
  verdict; Read alone had been misleading because of caching.
- Recovery: rebuild the approved version from conversation context, re-verify
  the marker greps flip (22 approved-marker hits, 0 rejected), then have the
  human confirm their editor buffer holds the restored version before further
  work — otherwise the next save clobbers it again.

## Implications / next actions

- [ ] Whenever a plan/doc goes through an approval gate **and** is co-edited by
      a human editor, re-verify the on-disk version against approved-version
      discriminator strings immediately before acting on it. Do not trust the
      Read cache; grep the file directly.
- This is **procedural, not project-specific** — any approved-artifact +
  live-editor-sync workflow has the same failure mode. Promotion candidate if
  it recurs outside this project.

## Pointers

- Plan file involved: `~/.claude/plans/noble-knitting-crown.md` (E13 decode KV
  egress, M2-S3b).
- Related class of gotcha: [[compression-subagent-drops-tracking-checkboxes]]
  (a rewrite pass silently losing reviewed content),
  [[derived-scripts-and-editing-a-running-script]] (editing files that
  something else is concurrently consuming).
