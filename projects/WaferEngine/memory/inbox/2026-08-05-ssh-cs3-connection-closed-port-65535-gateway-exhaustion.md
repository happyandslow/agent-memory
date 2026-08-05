# `ssh CS-3` → "Connection closed by UNKNOWN port 65535" = gateway connection exhaustion, not a local socket fault — 2026-08-05

**Project:** WaferEngine
**Author:** claude
**Status:** captured

## The situation this applies to

An interactive `ssh CS-3` suddenly fails at connect time with:

```
Connection closed by UNKNOWN port 65535
```

You wonder whether your local ssh multiplexing is broken, or whether too many
CS-3 sessions are open. You want to know what to check **without opening new
gateway connections** (which would make it worse).

## What is actually going on

- The error is the **EIDF gateway** closing the new forwarded channel (the
  ProxyJump `-W [cerebras]:22` hop) — a gateway-side refusal, **not** a broken
  local socket. Local ControlMasters still report "Master running"; that is a
  red herring.
- The `CS-3` alias has **no ControlMaster** (only `RemoteCommand` + `ProxyJump`),
  so **every** `ssh CS-3` opens a **fresh** gateway connection — nothing is
  reused. The automation alias `CS-3-cmd` **does** have a ControlMaster (the
  "warm path"), which is why automation keeps working while interactive login
  fails.
- Leftover long-lived interactive `ssh CS-3` sessions (e.g. a forgotten 6h one)
  each hold a gateway slot. With those plus the automation tunnel, new
  connections get refused — the leading diagnosis is a gateway connection cap /
  per-IP rate-limit (`MaxStartups` / fail2ban). *[unverified: the 65535-refusal
  → gateway-cap causation is diagnosis; retry-after-cleanup was not confirmed in
  this session.]*

## What to do

- **Check local state without new gateway connections:** `ps`/`ss` on the local
  ControlMaster sockets only — do not `ssh` to probe.
- **Free a slot:** kill leftover interactive `ssh CS-3` PIDs (the ProxyJump pair),
  then retry. **Preserve** the `CS-3-cmd` automation master — do **not**
  `rm ~/.ssh/cm/*` (that kills the warm path and forces a fresh OTP login).
- **Do not loop-retry** the failing `ssh CS-3` — repeated refusals risk a
  fail2ban IP lockout. Wait a few minutes; diagnose a real failure with
  `ssh -v CS-3` and read the first ~20 lines.

## Promotion candidate

Procedural, CS-3/EPCC-general (symptom → recipe, no specific run named) → fits
the **cs3-run** / **cs3-runner** skill's connection-troubleshooting section.

## Pointers

- Distinct from the run-transport death case (ssh dies mid device-run →
  orphaned wafer job) already recorded under WaferEngine-staging
  (`2026-07-21-cs3-ssh-death-orphans-wafer-job`); related: [[epcc-cs3-has-four-systems]].
