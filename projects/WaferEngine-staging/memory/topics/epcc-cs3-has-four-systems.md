---
summary: The EPCC CS-3 cluster has FOUR systems, not one — a guard that waits on "any wsjob exists" blocks on an idle cluster and costs wall-clock for nothing.
tags: [waferengine-staging, cs3, epcc, operations, cluster]
---

# EPCC CS-3 has FOUR systems — "any wsjob exists" is the wrong busy-test

Found 2026-07-31 after an E9 serve sat in a guard loop for ~40 minutes.

## The fact

`csctl get systems` lists **four** WSE-3 systems on this account:

```
xs20741   (busy)
xs20774   (idle)
xs20776   (idle)
xs20777   (idle)
```

A single running `wsjob` occupies **one** system. Three remain schedulable.

## The mistake it exposes

The guard used by the S30 / E9 drivers waits whenever the account has any job at all:

```bash
W=$(csctl get jobs 2>/dev/null | tail -n +2 | grep -c .)
if [ "${W:-0}" -gt 0 ] || [ "$C" = "502" ] ; then sleep 420; continue; fi
```

That treats a 4-system cluster as a 1-system cluster. **It blocked E9 for ~40 minutes against three idle
cards.** The intent was presumably to avoid colliding with *our own* concurrent runs (and with the known
EPCC 502 / pod-init flakiness), but as written it also blocks on **other tenants'** jobs, which is
neither necessary nor what we want.

## The right test

Compare running jobs against **available systems**, not against zero:

```bash
SYS=$(csctl get systems 2>/dev/null | tail -n +2 | grep -c .)
JOBS=$(csctl get jobs 2>/dev/null | tail -n +2 | grep -c .)
[ "$JOBS" -ge "$SYS" ] && wait     # only block when the cluster is genuinely full
```

Keep the 502 / empty-response part of the guard — that failure mode is real and unrelated
(see [[cs3-device-run-flakiness-and-safe-cancel]]).

⚠️ Unchanged: **never cancel a job you did not start.** This is a shared account; `csctl cancel` on
another tenant's job is out of bounds, and `cs3-run.sh`'s cancel path does exactly that, which is why
these drivers must not call it.

## Caveat I have not measured

Whether two of *our* jobs on two different systems contend for anything shared (host staging bandwidth,
the gateway, NFS on `$L`). Weight staging moves ~4 GB per build, so concurrent builds could contend on
the filesystem even when the wafers do not. Serve runs stage far less. Not tested — treat concurrent
*builds* with more caution than concurrent *serves*.

## Last updated

2026-07-31
