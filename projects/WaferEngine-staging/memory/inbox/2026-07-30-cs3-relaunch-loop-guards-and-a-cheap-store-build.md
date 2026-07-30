---
date: 2026-07-30
project: WaferEngine-staging
tags: [cs3-cluster, operations, automation, build, epcc, recipe]
---

# Automating "retry the CS-3 run when the 502 clears" — three things that bite, and a store build that takes 5 minutes instead of 20 — 2026-07-30

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured

## The situation this applies to

Half your CS-3 serve runs die on the EPCC ingress 502 (already captured in
[[2026-07-29-cs3-serve-runs-fail-about-half-the-time]]), so you want a loop that
checks periodically and relaunches when the cluster comes back. Or: you need a
new compiled store for a config that differs from an existing one only on the
decode side, and you do not want to pay ~20 minutes for it.

Four things learned doing exactly that.

## 1. You can tell a healthy EPCC ingress from a sick one with one curl

The 502 comes from the ingress at `10.27.24.65:443`. Probing it directly
separates "cluster is down" from "my job failed":

```
curl -s -o /dev/null -w "%{http_code}" -k --max-time 12 https://10.27.24.65:443/
```

- **404** — healthy. The reverse proxy is up and routing; it simply has no
  handler for `/`. This is what you see when runs succeed.
- **502** — the failure signature. Proxy up, upstream dead.
- **empty / 000** — the probe itself failed; treat as unhealthy.

Cheap enough to gate an automatic relaunch on, and it distinguishes the two
states that otherwise look identical from the job log.

Observed shape of an outage: two consecutive failures with the failure point
moving *earlier* (11 min, then 2 min 46 s) — that reads as the ingress degrading,
not as independent flakes, and is the signal to stop retrying rather than keep
hammering a shared service.

## 2. `pgrep -f "<pattern>"` matches your own command line — silently, and it looks exactly like the guard working

A relaunch guard must not start a second run on top of a live one. The obvious
guard is wrong:

```bash
if pgrep -f "launch_device.py --mode reload" >/dev/null; then echo busy; exit 0; fi
```

The shell running *that very line* has the pattern in its own command line, so
`pgrep` matches itself and the guard reports **busy forever**. Nothing is ever
relaunched, and the log line is identical to the guard doing its job.

Fix is the classic bracket trick — the regex `[l]aunch` matches `launch`, but the
literal `[l]aunch` in your own command line does not match the regex:

```bash
if pgrep -f "[l]aunch_device.py" >/dev/null; then ... fi
```

Verified both ways afterwards: with no run active the guard launches; with a run
active it prints `busy` and names the **real** PID.

Belt and braces: also check `csctl get jobs` is empty before launching — that
protects other tenants on the shared account, not just you.

## 3. A new store does not need a full build if only the decode side changed

`--build-phase decode` alone leaves a partial cache that `--mode reload` refuses.
But you do not need to recompile prefill if `src/prefill/**` and
`launch_prefill.py` are byte-unchanged and the new config differs only in
decode-side keys — the prefill ELF is genuinely identical.

Recipe: **pre-copy** `prefill/` and `tokenizer/` from a compatible store into the
new store directory, then run `--mode compile --build-phase decode`. With both
phases present the build calls `_finalize_cache` and rewrites
`build_manifest.json`, so the reload freshness gate passes.

**Measured: 4 min 56 s** including the 3.2 GB prefill copy, against ~20 minutes
for a full both-phase build. The prefill artifact contains no config-name string,
so the copy is clean.

⚠️ `--reuse-prefill-from` does **not** do this: `_resolve_reuse_store` requires
the source directory to be named after the *target* config, so it only supports
rebuilding the same config, not cross-config reuse.

## 4. The worker log cannot tell you which request file a run used

`_stage_request` stages whatever you pass to `--request` under the **fixed name**
`request_config/<test>/request.json` on the worker. The content is correct, but
the worker's `Run command` line therefore always reads `--request
request_config/<test>/request.json` — whether the run used `request.json` or
`request_m64.json`.

⇒ Never establish a run's parameters from the worker command line. Read them from
the run's own output (`results.json`) or the local invocation record.

## Implications / next actions

- [ ] Items 1 and 2 are **procedural and cross-project** — any "relaunch when the
      remote comes back" loop has the same two failure modes. Promotion candidate
      if a second project needs it; on its own probably not yet worth a skill.
- [ ] Item 3 is a concrete recipe worth folding into whatever note covers CS-3
      build mechanics at maintain time.

## Pointers

- Guard script as used: `we-m2bench/evidence/m2s2_guarded_launch.sh`.
- Related: [[2026-07-29-cs3-serve-runs-fail-about-half-the-time]] (the 502 rate
  itself; this note is what to *do* about it in automation).
- Session: M2-S2, 6 serve attempts / 3 completed, 2026-07-30.
