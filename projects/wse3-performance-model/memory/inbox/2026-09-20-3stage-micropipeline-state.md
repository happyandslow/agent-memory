# The 3-stage (A1/A2/A3) micro-pipeline: where it lives, what works, what's measured, and its limits — 2026-09-20

**Project:** wse3-performance-model
**Author:** claude
**Status:** captured — reference state for the 3-way pipeline comparison handoff.

## Situation this applies to

You are working on the layout-C "tall" 3-stage decoder micro-pipeline (split each
decoder layer into A1=QKV / A2=attn+O / A3=FFN, three thin 128-wide physical
stages, vs the original "fat" attn-block + ffn-block layout). You want to know
what is implemented, where, what it measures, the bugs already found, and the
per-layer throughput numbers — as the basis for the 8-block full-model comparison.

## Where the implementation is

**Single fused 3-stage block + within-block feedback ring** (this is a BLOCK
TESTBED with random weights, NOT a full model — no embed/head/sampling):
`demo/fused-block/xz-staircase/package/`
- `tall/src/tall_stage.csl` — the harness: `pipe_a1` (the A1 N-slot pipeline
  scheduler), stage-2/3 bodies, START/collector wiring. **SHA `40341434` = the
  FIXED version (see bug below).**
- `tall/src/group_link.csl` — A3→A1 feedback ring: per-slot landing, credit/ACK.
- `tall/src/group_strip.csl` + `tall/host/group_routing.py` — the router-only ACK
  aggregation strip + feedback/credit topology (single global credit, multicast
  to all A3 x=0 senders).
- `tall/src/decode.csl` — the qwen3-4b compute kernel (`kernel` module): a1/a2/
  ffn_layer_body, `select_pipe_slot` (pointer-swap ptr_X + RoPE into X_hold/
  freqs_hold). Weight tiles + KV cache are per-layer banks (`set_layer(l)`).
- `package/measurement.py` — the collector column (START in, time outputs).
- `package/run_case.py` — entry: `--variant tall|upstream --feedback --layers L
  --pipe-slots {1,2} --inflight-window W --capacity --bsz --prof`.
- **The baseline (impl 1 building block)**: `package/upstream/` —
  `launch_legacy_probe.py` + `src/legacy_stage.csl` = the original attn-block +
  ffn-block (256-wide) single layer, run with `--variant upstream`.

Run on CS-3 via `device.py --case <name> --options "<run_case args>"` (cs3-runner
skill; staging `/home/lexu/xzstair-cs3/package-xz` → `CS-3:~/rsync/xzstair-cs3-rsync/package-xz`).

## What works (verified on CS-3 this session)

- **Single-layer + serial feedback**: bit-correct. Serial feedback-2 = `TIMING
  68,151`/tok.
- **N-slot micro-pipeline** (`--pipe-slots N`, N=2 and N=4 tested): a **conservative
  cohort** of N positions through the layers (wait all N feedbacks before the next
  layer), async A1 forward sends with poll-yield. Output **byte-identical** to the
  CPU operation-order oracle (`actual.npy` SHA `f84a4426…`, 84,480 values) at both
  N=2 and N=4, full geometry.
- Gated: `--pipe-slots 1` = byte-identical serial; the fix is specialized to
  `layer_banks==2` (a `@comptime_assert`).

## Bugs / problems found (do not rediscover)

1. **RUNTIME-DIVISOR HARDWARE HANG (was mis-framed as a deadlock; RESOLVED).** The
   N-slot scheduler computed `frame_slot/frame_layer/frame_token` by dividing/
   remaindering a **runtime** `cohort_size()` → linked `__divhi3`/`__udivhi3` into
   the A1 ELF → the PE stalls at that first scheduler arithmetic on **device**
   (a single PE with no comm reproduces it; the same arithmetic PASSES in
   simulation). Serial used a comptime-constant divisor (`layer_banks`) → no
   helper → never hung. **Fix: shifts/masks** (`tick>>2`, `tick&3`, …). Full
   details + the frame-by-frame refutation of the deadlock theory:
   [[2026-09-18-pipe-slots2-deadlock-handoff]] and
   `docs/reports/2026-09-18-pipe-slots2-deadlock-investigation-handoff.md` and the
   separate debug session `demo/fused-block/xz-staircase/investigation-2026-09-18-debug2/`.
   **Lesson: a runtime (non-comptime) integer divisor in a hot CSL path can stall
   on WSE-3 while passing in sim — a sim-vs-device divergence, not scale/sync.**
2. **Widening N reintroduces the hang** unless `PIPE_SLOTS × layer_banks` stays a
   power of 2 (the shift trick). N=2→4 was safe (num_steps%4≤1); N=3 (→ cohort 6)
   would use runtime division → hang. Depth/slot generalization must respect this.
3. **The `PERIOD` collector metric is misleading for wide cohorts** — a cohort
   emits N outputs in a burst, so the median inter-arrival is deflated (N=4 PERIOD
   9,768 ≪ true 41,684). **Use span/(steps-1) = (last_arrival − first_arrival)/(n−1)
   for true throughput.** `TIMING = median cyc` is per-token LATENCY (grows with
   cohort), not throughput.

## Measured numbers (CS-3, prefill 1280, full geometry)

- **Per-stage compute (tall, single-layer prof):** A1(QKV) 4,909 · **A2(attn+O)
  7,746** · A3(FFN) 7,536 → **tall pipeline bottleneck = A2 = 7,746/layer** (grows
  with context: 9,578@5120, 13,957@15360).
- **Single-block feedback throughput (span-based):** serial 68,151/tok(2 layers);
  N=4 = **41,684/tok** = 20,842/layer = **1.63×** over serial. This is the SINGLE-
  block-feedback ceiling — it does NOT reach the A2 bottleneck (7,746) because the
  per-layer feedback roundtrip is only partly hidden by the cohort.
- **Baseline (legacy attn+ffn, single layer):** 26,529/tok combined; per-stage
  T_attn ≈ 11,680 (QKV+attn+O in one fat block) · T_ffn ≈ 4,931 → **baseline
  pipeline bottleneck = max = 11,680/layer**.
- **Isolated compute-bottleneck comparison (ignoring inter-block comm):** tall
  7,746 vs baseline 11,680 = **tall 1.51× faster at the bottleneck** — because the
  3-stage split moves the attn bottleneck from (QKV+attn+O) down to max(A1,A2,A3)=A2.

## Limits / open (why this can't just "run the whole model")

- **Block testbed only**: random weights, no embedding / LM head / sampling.
- **Within-block feedback caps at 2 layers** (piped guard) and **can't fit 36
  layers' weights in one block** (FFN UP/GATE/DOWN dominate per-PE SRAM, ~7KB/layer;
  36 layers ≫ 48KB). Full depth REQUIRES multiple physical blocks.
- **Within-block feedback is throughput-poor**: pays the A3→A1 roundtrip EVERY
  layer, pipeline only 3 stages deep → 20,842/layer, ~2.7× the ideal 7,746. A
  multi-block FORWARD pipeline (or "big-loop": 8 blocks forward, loop every ~8
  layers) pays the roundtrip once per pass and is ~24 stages deep → reaches ~A2.
- **Inter-block communication is the deciding unknown** — the 7,746 assumes
  inter-block hand-off ≤ A2; only a real multi-block build measures it.
- **SRAM of splitting**: weights+KV amortize (conserved when layers/block shrink);
  the NON-amortizable per-token working buffers (FFN silu/up_gate ~6KB/PE, attn
  softmax ~1.5KB, X/RoPE) are one copy PER BLOCK → duplicate ~N× when you split.

## Pointers

- 3-way comparison experiment handoff: `docs/reports/2026-09-20-3way-pipeline-comparison-experiment.md`.
- Prior captures: [[2026-09-17-tall-fine-grained-pipeline-and-per-stage-vs-context]] (per-stage vs context, ceiling), [[2026-09-18-pipe-slots2-deadlock-handoff]] (the runtime-divisor bug, corrected).
- Ring/credit diagram: `docs/diagrams/2026-09-18-feedback-credit-ring-deadlock.{excalidraw,svg,png}`.
- Skill: `cerebras-debugging` (sim-vs-device, artifact-SHA discipline, compile-memory-report-for-SRAM).
