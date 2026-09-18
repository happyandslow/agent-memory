# The N=2 fine-grained pipe compiles + starts but hangs on device; the candidate deadlock cycle is refuted and dump-core can't reach it — 2026-09-18

**Project:** wse3-performance-model
**Author:** claude
**Status:** captured — OPEN investigation, handed off to a fresh session

## Situation this applies to

You enabled the tall layout-C decoder's fine-grained pipeline (`--pipe-slots 2
--feedback --layers 2`, the N=2 position-slot cohort over the A1/A2/A3 feedback
ring, `demo/fused-block/xz-staircase/`) and it **deadlocks on CS-3**: compiles,
loads, starts executing (TCP handshake + GETFABRIC fine), then makes no progress
until bounded.py's 900s deadline kills it (exit 124). The serial path
(`--pipe-slots 1`) is byte-correct: **TIMING 68,151**. The mini oracle passes
bit-identical, so it is NOT a numerics bug. You are trying to find WHY it hangs.

## Findings

- **The device hang is real but its closing edge is NOT pinned.** Frame-by-frame
  static analysis (Codex, 2026-09-18) REFUTED the obvious candidate cycle. Do not
  re-derive "forward waits credit / credit waits forward": the feedback **credit
  (color 15) is a SINGLE GLOBAL all-or-nothing signal** — the router-only strip
  aggregates the whole group's ACKs (each A1 row's horizontal `try_ack` chain,
  then the strip's vertical chain) and emits ONE credit, multicast to ALL A3 x=0
  senders (`group_strip.csl:40`, `group_routing.py:68`). So (1) there is no
  partial-credit state: `C0` is emitted iff ALL A1 crossed their f0 forward gate
  (`tall_stage.csl:241`+`group_link.csl:93`); (2) "waiting to SEND feedback 0"
  cannot be a prerequisite for "CONSUMING f0 input" (source order A2→Z0→A3-feedback,
  `tall_stage.csl:434/478`) — that closing edge does not exist; (3) the poll-yield
  actually works — A3 waiting credit (`try_send` returns, `group_link.csl:138`) and
  A1 waiting on OQ/send-done (`tall_stage.csl:219`) do NOT hold the CE, so there is
  no proven pure forward-credit hang; (4) the barrier-skew "delay" is not shown to
  become permanent (f1 layer-0 admission doesn't check feedback-ready,
  `tall_stage.csl:199`).
- **dump-core is a dead end for this hang.** `dump_core` is simfab-only
  (`SimfabConfig(dump_core=True)`; no device-runtime dump_core in the SDK), and
  simfab can't reach 128-wide (the scaled adapter supports ×1/2/4 only, all PASS;
  ×8 unavailable). So **no configuration both triggers the hang AND can dump a
  core** — the reason nobody has pinned it.
- Mini oracle bit-identical (single-layer, serial feedback, N=2 feedback tokens
  0-23, 3-layer tokens 0-6); negative controls fail correctly. Correct at mini
  scale; mini just never fills the queues.

## Why it matters / how to apply

Saves a fresh session from (a) re-deriving the refuted cycle and (b) burning CS-3
jobs trying to dump a device core that the SDK can't produce. The three viable
paths are in the handoff: **(1) get the REAL 128-wide geometry into simfab** (only
place hang + dump_core + `read_slot_core.py` coexist — highest value), (2) on-device
phase-word readback buffer, (3) geometry bisect (80/96-wide) for a simfab-able hang.
The whole `demo/` tree is UNTRACKED — review via the `.patch`, not `git diff`.

## Pointers

- **Full handoff:** `docs/reports/2026-09-18-pipe-slots2-deadlock-investigation-handoff.md`
  (repro cmds, code map, refutation, dead ends, paths, landmines).
- Implementation (untracked, gated on `--pipe-slots 2`): `package/tall/src/{tall_stage,group_link,group_strip,decode}.csl`, `package/tall/host/group_routing.py`, `package/{run_case.py, tall/launch_tall.py}`. Exact diff: `slot-evidence-2026-09-17/slot-implementation.patch`.
- Design + progress arg: `SLOTS-VERIFICATION.md`. Codex debug: `slot-debug-2026-09-18/` (`REPORT.md`, `read_slot_core.py`, `scaled_slot_check.py`, `raw-evidence.tar`).
- Ring diagram: `docs/diagrams/2026-09-18-feedback-credit-ring-deadlock.{excalidraw,svg,png}`.
- Related: [[2026-09-17-tall-fine-grained-pipeline-and-per-stage-vs-context]] (per-stage timing, ~2.5–3.7× ceiling, the value case), `no-local-large-compiles`, `simfab-stall-diagnosis-recipe`.
