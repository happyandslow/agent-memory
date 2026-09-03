# Frozen-hash pin cascade after an intentional source change — some pins are baseline pins and must NOT be updated — 2026-09-03

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured

## The situation this applies to

You intentionally changed a source file covered by frozen-closure hash pins
(here: Part 2/3 changes to `decode.csl` + production `launch.py` in
`models/qwen3_1p7b-decode-ragged-batch/`) and the full host suite lights up
with dozens of failures that look alarming (71 failed + 14 errors out of
~975). You need to re-green the suite without corrupting any binding.

## What happened / finding

- Every one of the 85 failures triaged to **pin-literal drift**, zero
  behavioral regressions. Classify first; don't debug individual tests.
- Update pins in **dependency order**: C2 → streaming reference → probe →
  periphery (named_faults, trace_adapter, integrated). Updating downstream
  first just re-breaks when upstream pins move.
- **The trap:** not every stale-looking hash is yours to update. Some pins
  bind the **main baseline model** (e.g. the baseline `launch.py` hash
  `056060…` in named_faults and integrated tests) and must stay untouched —
  a blanket search-and-replace of drifted hashes silently rebinds the
  baseline to the changed tree and destroys the A/B meaning of those gates.
- named_faults pins are **two-level**: the overlay-source revision hash plus
  per-fault after-hashes. Recompute all six programmatically from the new
  source rather than hand-patching.
- The A1 physical-oracle chain is frozen at commit `5bb8504`; after the
  source moves, re-green it by **replaying the probe + closure from the git
  snapshot of that commit**, not from the live tree (16/16 gates passed this
  way).
- Bonus: re-capturing the cap-2048 record against the new source produced a
  **bit-identical tensor manifest**, so the existing full-scale NumPy
  references (~100 min/case to recompute) remained valid without rerunning.
- End state: full host suite 974/974 green.

## Implications / next actions

- [ ] Next intentional `decode.csl`/`launch.py` change: expect this cascade,
      triage-by-classification first, follow the dependency order, and grep
      for baseline-model pins before any bulk hash replacement.

## Pointers

- Work repo: `models/qwen3_1p7b-decode-ragged-batch/tests/` (C2, streaming,
  probe, named_faults, trace_adapter, integrated, `s0_a1_physical_oracle.py`)
- Session: M1b-S0 Part 2+3 test session, 2026-09-02/03 (Part 2 harness
  closure/TOCTOU fixes + Part 3 production `launch.py` validation)
- Related: [[2026-09-02-m1b-s0-part1-commit-and-part2-parallel-status]]
