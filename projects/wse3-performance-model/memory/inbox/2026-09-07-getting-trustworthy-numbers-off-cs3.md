# Getting trustworthy numbers off CS-3 — 2026-09-07

**Project:** wse3-performance-model
**Author:** claude
**Status:** captured
**Promotion signal:** PROCEDURAL and recurring — this is method for a class of
situations (bring-up and measurement on a wafer-scale device with an
expensive, slow, low-observability run loop), not a fact about the 4B model.
Candidate for a skill.

## The situation this applies to

You are bringing up a new geometry or layout on CS-3. A device job either
wedges (runs far past its normal window, producing no round-0 record, while
the appliance holds the launcher's stdout until exit so the log shows nothing),
or it completes and hands you a number that looks like a measurement. Device
jobs are minutes of wall time each, the account is shared and multi-tenant, a
wedged job holds a wafer slot, and the simulator is a different toolchain that
has repeatedly accepted what silicon rejects.

## Finding 1 — reproduce on the simulator before spending a second device job

Across this session: **device wedges root-caused at mini scale in the
simulator, 3 for 3. Root-caused by debugging on the device, 0.** Every wedge
turned out to be reproducible at a mini geometry once the right axis was
varied, at zero device cost and in minutes rather than a job per hypothesis.

- Enabling technique worth keeping: a host mode that **sends a round, sleeps,
  STOPS the simulator, then reads exported per-stage progress counters**
  (symbol reads work after a stop). Three probe iterations walked the failure
  frontier — "row 0 attention finished, row 0 FFN consumed everything, row 1
  attention stuck in its first receive" — which located the fault to a specific
  hop without a single device job.
- Corollary: **a bisect that varies one thing** beats a plausible mechanism. A
  hypothesis about a cross-band transit route survived review, a device-side
  fix, and a rewrite; it died in one bisect that moved the probe to a one-hop
  lane and still failed.

## Finding 2 — the instrument was measuring something else, four ways

Every one of these produced a plausible-looking number that was not the
number claimed. All four were caught, but only because someone asked what the
instrument was actually doing.

- **An oracle running its own chain.** The numpy reference generated its own
  argmax continuation while the device sampled from its top-k, so per-step
  "overlap" measured *sampling divergence*, not model error, and decayed by
  construction after the first divergence. Earlier runs that reported 1.000 at
  every step did so only because their sampled chain happened to track argmax.
  Fix: feed the oracle the device's own sampled chain.
- **A median that absorbed a partner's wait.** A pipeline stage's *median*
  busy window rises with context because it includes waiting on the pacing
  stage; its *floor* is flat. Reading the median would have concluded that the
  FFN carries context slope, which is false. Read the floor for a non-pacing
  stage.
- **A capacity sweep that measured nothing.** Per-token cost tracks the *live*
  context (the score GEMV length), not the declared maximum. A run with a large
  MAX_SEQ_LEN and the old small prefill reports the small-context number while
  looking like a measurement. Every point of a capacity curve must be prefilled
  to its own depth.
- **A probe that changed what it measured.** The block-TSC profiler's ring
  buffers cost per-PE SRAM and fail to link above a lower context than the
  kernel itself; and a probe lane placed at the collector row's westmost cell
  is silently dropped. Gates that run with the profiler *off* do not exercise
  it — the probe path was the one thing a green mini gate had never tested, and
  it cost a wedged device job.

## Finding 3 — geometry parameters break subsystems the gates do not run

Seen twice, and worth checking by default: **"correct at one geometry, silently
wrong at another, invisible in simulation because simulation never ran that
geometry."** Both instances were a per-PE role derived from a folded coordinate
(`row mod K`, `row / K`) that produced phantom duplicates when the fold pitch
changed but the region height did not, and a route installed for a geometry
that no longer existed. When a geometry parameter moves, enumerate every
subsystem whose behaviour is a function of it — **including measurement
scaffolding, which the gates usually disable** — and exercise each at the new
geometry before spending a device job.

## Finding 4 — the gates, ranked by strength

Worth stating because weaker gates were repeatedly reported in language that
implied a stronger one.

1. **Byte-identity against a prior build** — available whenever a change does
   not move values or addresses. 1,000 device records matching bit for bit is
   the strongest evidence available and needs no interpretation.
2. **A negative control** — the *unpatched* tree refusing to compile with the
   value and line named, and the patched tree running the same config. Proves
   *removal*; byte-identity only proves *inertness*.
3. **Oracle plus bounded divergence** — necessary when reductions re-associate
   and byte-identity is impossible by construction. Name it explicitly so a
   bounded-divergence pass is never read as byte-identity.

## Implications / next actions

- [ ] Propose as a skill: the trigger is "a device/accelerator bring-up where
      runs are slow, shared and low-observability, and a measurement or gate is
      about to be believed". The content is findings 1–4 stated without naming
      this kernel.

## Pointers

- `docs/reports/2026-09-04-4b-wide-layer-session-report.md` Rounds 73, 99–103,
  115 (each finding with its evidence)
- `demo/qwen3-4b-thin-stage/one-layer-cuts/cut2-status.md`,
  `.../vstack/status.md`, `.../stride-lift/status.md`
- private memory `wse3-color-registration-and-repaint-landmines.md` items 7–9
