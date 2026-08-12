# WaferEngine-staging Manual Conflicts

Last reviewed: 2026-07-29

## Needs Le/manual resolution

- **2026-07-29 — an in-repo "Failed approaches" entry appears to be wrong, and the
  correction is unconfirmed.** `PROGRESS.md` records that PR #14 demoted the `e2e` on-chip
  KV relay to inert filler, not config-revivable. A direct diff says otherwise for `e2e`
  (three `KV_TRANSFER: 1` configs already shipped on `main`; `build_relay` identical apart
  from whitespace; `src/relay.csl` still present at PR #14) — the claim holds only for
  **`e2e-pdSeparate`**. It looks like a model mix-up. **Not confirmed by Le**, and it
  changes an adopt-vs-port input in the convenient direction (adoption costs *less* than
  recorded), which is exactly when a correction deserves a second pair of eyes. See
  [[standalone-vs-integrated-kernel-parity]].
- **2026-07-29 — two in-repo contract lines are now known-stale and were not edited.**
  `milestones/M1-intra-pe-reuse.md § S0.2` says *"slot empty ⇔ `iter_num_bank[layer][slot]
  == 0`"*, but occupancy is a **host** judgement under D4; and the grep checklist lists S1
  as the owner of adding that dimension, which should read "not needed, superseded". Left
  for whoever next edits that milestone — flagged so it is not re-derived from the doc.
- *(Raised by the drain, checked, NOT a conflict — recorded so it is not re-raised)* two
  items looked like contradictions and are not: (a) `m2-s0-baseline-and-timer-provenance.md`
  still contains the string `15 MB/s`, but every occurrence is inside the section explaining
  **why that number is wrong** — correct usage, not a live figure; (b) `ROADMAP.md` was
  reported as still carrying the old "~1.3–1.5 GB/s, derived by assuming a 256-token chunk
  payload". It no longer does — it was updated the same day to the code-derived payload and
  the measured **1.426 GB/s**. The drain worked from the capture's quotation of ROADMAP, not
  from the current file.
- *(Resolved this pass, recorded for traceability)* `memory/project.md` carried
  **"Real Qwen3 weights are NOT wired into any model"**. True for the standalone kernels
  and the `main`-line fused models; **false for `e2e-pdSeparate` at PR #14**, which bakes
  real HF weights and has now been run end to end on real WSE-3. Corrected in place with
  the scope made explicit.

## Promotion candidates / manual follow-up

- 2026-07-22: Consider promoting the retain-review heuristic "distinguish carried-over state from state recomputed from a carried counter" to a recurring CSL/retain review skill.
- 2026-07-22: Consider updating the `cs3-runner` skill for ssh transport death: `rc=255` can bypass `csctl cancel`; check for orphan wafer jobs on reconnect.
- 2026-07-22: Consider updating the TSC/device-staging guidance: this e2e model's `cslc_bin` inline cap breaks `<time>.get_timestamp`, and new `.csl` files must be added to `FILES_TO_STAGE`.
- 2026-07-22: Consider promoting/atlas-linking the prefill metainfo review heuristic: per-request metainfo rides two channels (i32 token-id prepend + fp16 X-tile append), bridged at `ht_head`, so widen both paths together.
- 2026-07-23: Consider updating the `csl-color-audit` skill/docs with decode-layout caveats: predicted floorplans can include spurious fused-prefill regions, narrow helper PEs render as badges/side-table rows, and the matrix view omits switch/router helper PEs such as KV-ingress adaptor/injector/demux/mux tasks.
- 2026-07-23: Consider promoting the force-decode/F-dimension review heuristic: when adding a per-request count to a lock-step fabric loop, keep shared-color producer/consumer counts additive until both sides are deliberately mirrored; F=1 can hide an F>1 color imbalance.
- 2026-07-23: Consider promoting the performance-attribution heuristic from S6b: an F-sweep curve shape separates skip-compute (linear per forced step) from pipeline/resource fill (saturating/knee) better than a single mixed timing point.
- 2026-07-24: Consider promoting the host-side serving/control placement rule to repo convention docs or a review skill: while standalone kernel forms are still converging, per-kernel host control helpers belong beside `launch.py`; extract to `waferengine/engine/` only after compiled-kernel versioning settles.
- 2026-07-25: Consider updating the `meshagent-sync` skill/protocol: never `patch` a Markdown bulleted-list region in ContextBase/Outline mirrors because sibling list items can be silently dropped; re-mirror via header replace + append and verify mid-file plus late-file sentinels.
- 2026-07-25: Consider updating the `meshagent-sync`/checkpoint protocol to list/fetch existing same-day Logs and recent mirror `updatedAt` before creating a new session log or re-mirroring durable docs, to avoid duplicating parallel-session work.
- 2026-07-25: Consider promoting the git branch-status verification rule: before asserting commit/merge state, verify live branch topology and feature content; under squash merges, `merge-base --is-ancestor <original-tip>` can false-negative even when the branch contains the feature.
- 2026-07-26: Consider promoting the per-request-dimension review heuristic: before adding a slot/request axis to a lockstep kernel, identify which invariants the old uniformity enforced for free (for M1 decode, equal active-lane length survives only as a host/test obligation because scalar `iter_num` is also the packed score stride).
- 2026-08-10: Consider promoting the Git-safety rule from `memory/inbox/2026-08-08-git-stash-violates-a-preserve-index-ban.md`: a “preserve the index / do not mutate Git state” contract bans `git stash` too, because stash/pop mutates the index and worktree and can collapse staged-vs-unstaged boundaries.
- 2026-08-12: Consider promoting the encapsulation-refactor review rule from `memory/inbox/2026-08-11-encapsulation-refactor-needs-a-source-boundary-test.md`: when the change goal is ownership/boundary closure rather than behaviour, remove test-only mutable escape hatches, expose immutable evidence, and add a source-boundary regression test.
- 2026-08-12: Consider promoting the source-comment cleanup gate from `memory/inbox/2026-08-11-source-comment-lossless-compression.md`: for broad comment/docstring cleanups, compare docstring-stripped ASTs, run `git diff --check`, run the relevant suite, and verify the index boundary before/after.

### 2026-07-29 — one consolidated proposal, because seven captures turned out to be one lesson

The 2026-07-26 → 07-29 captures produced seven separate "promotion candidate" flags. Reading
them together, **six are the same failure**: *something that looks like evidence, isn't* — and
in every case it failed **silently**, reporting the same word or shape as a real result.

| the thing that looked like evidence | why it wasn't |
|---|---|
| a negative-control config printing PASS | an unknown JSON key defaulted back to the baseline, so the red test became a second copy of the green one |
| a device-side check printing PASS | it compared two empty arrays (`plen == 0` since S6a) — PASS having compared zero bytes |
| a numpy oracle agreeing with the device | the oracle contains a **second copy of the formula under test**, so it reproduces the bug it was meant to catch |
| a quoted bandwidth in four durable docs | its denominator came from a **prose phrase**, not a timer; the original author's "measured-ish" hedge was dropped by every citation |
| a branch someone linked you to, with committed result files | a **snapshot with a date** — the problem it showed had already been fixed 5 commits downstream |
| a benchmark request set with a familiar name | the name described the source corpus, not how it is **driven** — "MT" (multi-turn) driven single-turn, so it exercises zero reuse |
| a fit with R² = 0.998 | R² is invariant under an x-axis rescale, so it validates linearity and says **nothing** about whether you fitted the right variable |

⇒ **Proposal: one skill, "before you trust this as evidence, check what it shares with the
thing under test."** Trigger vocabulary should be symptoms, not terms — *a red test passes; a
check passes on empty input; the oracle agrees; a number everyone quotes; a branch someone
linked you to; a benchmark whose name matches your topic; a suspiciously good fit.* Each row
above is a worked example with a concrete tell. This is procedural, project-independent, and
has now recurred **seven times in four days** across two different milestones, which is the
promotion bar met several times over.

Two riders that did **not** fold into the above and stay separate:

- **`cs3-runner` skill, two updates** (extends the standing 2026-07-22 entry): its timeout path
  calls `cancel-mine`, which is unsafe on this **shared** account; and remote `nohup setsid` +
  log polling is the safer launch pattern because it also survives the rc=255 transport death.
  Add the observed failure rate — 3 of 5 identical serve runs died on EPCC ingress 502 /
  pod-init failures — so plans budget **attempts, not successes**.
- **"Report a performance number with its setting"** (Le's standing instruction, 2026-07-28):
  model size/shape, real vs mock weights, deployment scenario, geometry + config, batch,
  workload shape, machine, and `n`. Currently written into this project's `WORKFLOW.md` only,
  so other projects have to remember to look. Procedural and cross-project ⇒ skill material.
  Pairs naturally with the consolidated proposal above: the setting is what makes a number
  checkable in the first place.

Two further procedural rules worth carrying inside the consolidated skill rather than as their
own entries: **only destination addresses take a new storage axis** (a source buffer indexed by
the new axis reads into a neighbouring region — same type, same range, no trap), and **two
copies of an addressing formula will drift** — the second copy is where the bug will be. Also:
**before declaring a case impossible, check whether the impossibility came from an
implementation choice you assumed** (here, take-over vs ride-along semantics turned "mixed
hit/miss batches need ragged support" into a non-problem).
