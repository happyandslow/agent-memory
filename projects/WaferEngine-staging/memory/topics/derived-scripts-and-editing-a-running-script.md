---
summary: A chained remote job never fires, or a long-running script suddenly executes garbage — two traps in `sed`-derived driver scripts
tags: [WaferEngine-staging, drained-inbox, 2026-07-30]
---

# A chained remote job never fires, or a long-running script suddenly executes garbage — two traps in `sed`-derived driver scripts

This topic was created by the 2026-08-03 maintain pass from a dated inbox capture. Keep it as the durable, topic-scoped home for the finding; the original capture is marked drained.

## Drained capture — 2026-07-30

Source: `memory/inbox/2026-07-30-derived-scripts-and-editing-a-running-script.md`

# A chained remote job never fires, or a long-running script suddenly executes garbage — two traps in `sed`-derived driver scripts

Date: 2026-07-30 · EPCC CS-3, M2-S1 overnight runs

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured

**Promotion signal: procedural, not project-specific.** This is a method-level trap for any
long-running remote job driven by shell scripts; nothing about it is Cerebras- or
WaferEngine-specific. Candidate for a skill rather than a topic — see § promotion.

## The situation this applies to

You are running multi-stage work on a shared cluster where each stage takes 5–20 minutes, the
ssh transport is unreliable, and you want the next stage to start without you. The pattern that
works is a **server-side chain**: a `setsid nohup` watcher that polls the previous stage's log
for its completion marker and launches the next stage itself, so losing the ssh session costs
nothing. You produce the next stage's scripts by `sed`-ing the previous stage's.

Two things then go wrong, both silently.

## Trap 1 — the derived script builds the right thing but announces the wrong name

`sed -e "s/_s1b/_s1c/g"` correctly rewrote `--config …_s1c.json` and `--staging …_s1c` (both
contain the underscore) but left the script's own progress markers as `[m2s1b]` — `m2s1b` has
no `_` before `s1b`, so the pattern never matched. The watcher was written to wait for
`[m2s1c] build rc=0`, which the build would never print.

**Symptom:** the build completes normally, the chain sits there and eventually times out, and
nothing in either log says why. Worse variant seen the same night: the watcher's target log
filename *also* escaped the `sed` (`s1b_build.log`), so it watched the **previous stage's**
finished log, matched instantly, and launched the next stage against a store that did not exist
yet — failing in ~10 s with a confusing "no cache at …" error.

**Rule:** a marker string and the path it is grepped from must be produced by the same
substitution as the thing they describe. Safer: **write the derived script out in full rather
than `sed`-ing it**, or make the watcher grep a *stage-specific log file* for a
*stage-agnostic* marker (`grep "build rc=0" "$THIS_STAGE_LOG"`), so only one of the two has to
be right.

## Trap 2 — do not edit a script that is currently running

Having found trap 1, the obvious fix is to correct the marker in the build script. **Do not.**
`bash` reads a script **lazily**, by byte offset, as it executes; rewriting the file underneath
a running instance makes it resume at the old offset in the new bytes and execute whatever
happens to be there. For a script that is mid-way through a 17-minute compile, this is a
genuinely dangerous edit for no benefit.

**Rule:** when a running script and its watcher disagree, **fix the watcher** — it has not
started its critical section yet, and it is cheap to kill and relaunch. Leave the running
script alone and correct it after it exits.

## Implications / next actions

- Both traps cost ~10 minutes and one wasted job launch on 2026-07-30; neither produced an
  error message that pointed at the cause.
- [ ] Consider promoting to a skill covering long-running remote job chaining: `setsid nohup`
      + log-marker watcher, stage-specific log / stage-agnostic marker, never edit a running
      script, and "batch many remote commands into one ssh call" (the shared ControlMaster has
      a finite session budget — see `cs3-device-run-flakiness-and-safe-cancel`).

## Pointers

- CS-3 `/home/eidf217/eidf217/congjiehe/lexu/m2bench/m2s1{b,c}_{build,chain,chain2}.sh` and
  `logs/s1{b,c}_*.log`.
- Related: auto-memory `cs3-device-run-flakiness-and-safe-cancel` (drive runs with remote
  `nohup setsid`; automation must use the `CS-3-cmd` alias).

## Update — 2026-08-19

Source: `memory/inbox/2026-08-18-approved-plan-can-be-silently-reverted-by-editor-sync.md`

An approved plan file can silently revert if a human editor buffer still holds an older version and writes it back after an agent/review loop finishes. Before implementing an approved plan, verify the on-disk bytes directly with discriminator strings that exist only in the approved version and only in the rejected version; do not rely on an agent Read cache. In the E13 decode-KV-egress plan, approved markers such as `TOP_K=1`, `dbg_force_eos_step`, and `free-run greedy` disappeared while rejected markers such as `aligned PRNG` and `force/bounded-step` reappeared. Recovery was to rebuild the approved version, re-run the marker greps until approved hits were present and rejected hits were zero, then have the human confirm their editor buffer was also updated before continuing.

Promotion signal: this is procedural and applies to any approved-artifact + live-editor-sync workflow. It pairs with the existing rules in this topic: avoid editing files while another process is consuming them, and verify the exact bytes being acted on.
