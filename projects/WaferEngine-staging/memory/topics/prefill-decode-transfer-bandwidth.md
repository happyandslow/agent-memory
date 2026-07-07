---
summary: Effective-bandwidth study for qwen3 e2e prefill-to-decode KV handoff including transform compute and wire time.
tags: [waferengine-staging, kv-cache, bandwidth, prefill-decode, measurement]
---

# Prefill→Decode KV-Cache Transfer Bandwidth (qwen3_1p7b-e2e)

**Tracking topic — started 2026-07-06.** Goal: characterize the *effective
bandwidth* of moving the KV cache from the prefill block region to the decode
block region in the fused on-chip `qwen3_1p7b-e2e` model. The metric of interest
counts **both** the on-fabric data **transfer** (the north shift through the relay
seam) **and** the data **transformation / compute** (the on-PE gather + transpose +
re-layout that makes the tiles landable). i.e. bandwidth = (KV bytes delivered) /
(wall time from "prefill KV ready" to "decode cache populated"), *not* just the
seam wire time.

This is exploration-in-progress: the mechanism is mapped from the source; **no
measurement harness exists yet** (see Open questions / next actions). Related:
[[kv-cache-policy-tradeoffs]], [[e2e-pdSeparate-device-validation]],
[[standalone-vs-integrated-kernel-parity]].

## Why "transfer" here is mostly compute, not wire

The handoff is **not** a flat memcpy across the seam. The seam itself is passive
wire (colors 17/21 painted SOUTH→NORTH; `src/relay.csl` has no tasks). The
expensive work is the on-PE re-arrangement that happens on either side so a tile
lands in the *right PE* in the *right memory order*. Any honest bandwidth number
must include those stages — otherwise it measures a wire that is idle most of the
time.

End-to-end the handoff decomposes into three timed segments:

| Segment | Where | Nature | Code |
|---|---|---|---|
| **A. Prefill gather + transform** | prefill block region | short-range fabric comm **+ local compute** | `prefill.csl` `kv_step` states 0–3 |
| **B. North shift through seam** | prefill → relay → decode | inter-region **wire** (store-and-forward) | `kv_step` state 4 → `kv_north_shift` |
| **C. Decode receive + write** | decode block region | wire recv **+ local compute** (cache write) | `decode.csl` `kv_ingress` |

Segment A alone is a per-(layer, K|V) 4-state machine: W-sweep → E-sweep →
N-emit → S-emit, and only after that a `kv_transform()` re-lays each tile into
decode slab order (K stays interleaved = identity; V is transposed in-tile
`[f][b][s]→[b][s][f]`). Segment C re-lays the received buffer into `XKCache_tile`
/ `XVCache_tile`. So two full transposes/re-layouts bracket one wire shift.

## The setup (visualization)

Floorplan of the co-resident layout is saved as an artifact in this repo:

- `assets/prefill-decode-transfer/e2e-floorplan.html` — theme-aware source (open in any browser)
- `assets/prefill-decode-transfer/e2e-floorplan.pdf` — 2-page static render

It shows decode (north, rows 1–16), the `Pw×2` relay seam (rows 17–18), and
prefill (south, rows 19–34), all sharing block columns 8–23 because both halves
place block-column 0 at the same `PLACE_X = HT_WIDTH_tail + 4`. That column
alignment is what makes segment B a straight vertical (north) shift — decode PE
on column *c* sits directly above the prefill PE on column *c*. The picture is
just the *static geometry*; it does not yet carry any timing/bandwidth numbers.

## How the handoff works (reading summary, 2026-07-06)

Traced from `models/qwen3_1p7b-e2e/`. Enabled by `KV_TRANSFER=1`; guarded so both
halves agree on `PREFILL_LEN`, `bsz`, `n_layers`, and prompt ≤ decode `MAX_SEQ_LEN`
(`launch.py:2771-2780`).

**Payload.** After prefill finishes all layers, each prefill block PE holds its
slice of projected **K** (post QK-Norm + RoPE) and raw **V**, one tile per layer
(`prefill.csl:687-691`).

**Segment A — prefill egress gather + transform** (`prefill.csl:762-808`), per
(layer, K|V):
1. state 0 W-sweep + state 1 E-sweep funnel the row's tiles so the **diagonal PE**
   holds the whole row (`comm_pe.csl:888` `kv_sweep`).
2. state 2 N-emit + state 3 S-emit do the column exchange so tile `(lx,ly)` lands
   on PE `(ly,lx)` (a transpose), then `kv_transform()` re-lays into decode order.

**Segment B — north shift** (`prefill.csl:801-807`, `comm_pe.csl:985-998`
`kv_north_shift`): a blocking store-and-forward pipeline. Row `gy` injects its own
tile then forwards `total_y_pes - gy - 1` more coming up from below. Runs
`2*max_layers_per_block` phases back-to-back (K and V per layer). Colors alternate
17/21 by fabric-row parity so a PE never sends and receives on the same color.

**Segment C — decode ingress** (`decode.csl:1348-1398` `kv_ingress`), runs
synchronously before decode starts (block PEs idle until cache filled,
`decode.csl:1480-1484`): decode row `r` receives `r+1` tiles and forwards all but
the last; the kept tile is its prefill mirror's, already in decode slab order. It
is then written into `XKCache_tile` (K, per-feature rows) / `XVCache_tile` (V,
per-batch blocks). `kv_flush_then_init()` drains OQ7 and rebinds queue 7 to the
broadcast color, then decode proceeds with `iter_num = prefill_len_per_pe`.

## Data-volume math (for bandwidth = bytes / time)

Per prefill block PE, per (layer, K|V) phase, the shifted tile is
`kv_tile_size = kv_dim_per_pe * reduce_len` fp16 elements, where
`reduce_len = bsz * seq_len_per_pe` (`prefill.csl:153,165`). Decode's per-phase
receive buffer is `kv_in_tile = bsz * kv_dim_per_pe * prefill_len_per_pe`
(`decode.csl:1334`).

Total KV bytes that must cross the seam (whole prefill block region → decode):

```
bytes ≈ (Pw · Ph)                        # prefill block PEs, each holds a tile
      · (2 · max_layers_per_block)       # K and V, per layer-in-block
      · kv_dim_per_pe · bsz · seq_len_per_pe   # elements per tile
      · 2                                # fp16 = 2 bytes
```

**TODO:** plug in concrete values for `test_sim_2x2blk_kv` /
`test_device_2x2blk_kv` — the config JSONs did not expose `bsz`, `kv_dim_per_pe`,
`seq_len_per_pe`, `max_layers_per_block` directly (derived in `launch.py`); pull
the resolved values from a run's printout and compute the byte total, then divide
by the measured A+B+C wall time.

## Measurement design (2026-07-06)

**Timing mechanism:** per-PE TSC via the CSL `<time>` library — 48-bit
free-running counter, read as 3×u16 by `get_timestamp`, after `enable_tsc`.
Convert cycles→time at **1.1 GHz** (the WaferEngine WSE-3 fabric constant, in
`bench/.../utils.py` `FREQ_GHZ=1.1` and `pdSeparate/launch.py:3125` — **not** the
SDK bandwidth-test's 0.85 GHz). Full how-to in the skill
`cerebras-sdk-pe-timestamp-timing` (updated this session: freq reconciliation +
single-PE segment-profiler). The repo already ships a reusable timer module:
`models/qwen3_1p7b-decode/bench/layer_block/src/time_pe.csl` (+ host decode in
`utils.py`) — copy it, don't re-derive.

**Why two PE sets / the window.** Segment A (gather+transform) runs on **prefill**
block PEs; segment C (receive+write) runs on **decode** block PEs; segment B (north
shift) couples them through the seam. No single PE observes both ends, so a *true*
end-to-end number needs cross-PE timestamps with reference correction. Anchors:
- **t0** — prefill KV ready: entry to `start_kv_transfer()` (`prefill.csl:762`).
- **t1** — segment A done: after `kv_step` states 0–3 for all layers (`prefill.csl:793-799`).
- **t2** — segment B done: after `kv_step` state 4 north shift (`prefill.csl:801-807`),
  sampled on the **top prefill row** (adjacent to seam; forwards all rows below it).
- **t3** — decode cache populated: `kv_flush_then_init()` → `kv_init_cont`
  (`decode.csl:1397`), sampled on the **south-most decode row** (`r=Ph-1`, receives
  `r+1` tiles, finishes last = the ingress critical path).

Report A=t1−t0, B=t2−t1, C (decode ingress span), and total delivery=t3−t0.

**Staged plan.**
1. **Phase 1 — per-PE segment split (no cross-region alignment).** Use the
   single-PE low-32-bit segment profiler (`seg_begin`/`seg_tick`, exact via
   modular subtraction for spans <2^32 cyc ≈ 3.6 ms @1.1GHz). Prefill PE: tick at
   A-done and B-local-done; decode PE: tick at C-done. Each PE times *itself*, so
   no ref-correction — gives the **compute (A + C-write) vs wire (B)** breakdown
   directly. Reduce across PEs by max (slowest gather / longest ingress tail).
2. **Phase 2 — headline end-to-end GB/s.** Cross-PE ref-corrected t0(prefill) →
   t3(decode). e2e is `memcpy_required=False` (direct streams), so use the
   direct-stream sync/tic/toc retrofit from companion skill
   `cerebras-sdk-direct-stream-tsc-sync-tic-toc`. Bandwidth = KV bytes / (t3−t0).

**Readback.** Export the packed cycle buffers as symbols. **Sim first**:
`read_symbol` (sim-only, cheap, no simfab trace needed) after
`./run_sim.sh model_config/test_sim_2x2blk_kv.json`. **Device**: add a small
copy-mode `memcpy_d2h` of the packed buffers, or piggyback the existing
`is_tsc_pe` fabric-burst path used by `ht_tail.csl`.

**Byte total** (fill for the target config from the `launch.py` printout):
`bytes = (Pw·Ph) · (2·max_layers_per_block) · (kv_dim_per_pe·bsz·seq_len_per_pe) · 2`.
For `test_sim_2x2blk_kv`: Pw=Ph=16, **n_layers=8 over 2×2=4 blocks →
max_layers_per_block=2** (not 4 — layers distribute over *all* blocks, X and Y),
bsz=1, kv_dim_per_pe=4, transferred seq_len_per_pe=2 (PREFILL_LEN=16 / P_BLOCK_SIZE=8)
⇒ **16 KiB** total (`256 · 4 · (4·1·2) · 2`).

**Config caveat (important).** The shipped **sim** config is a **dim=64 toy**
(n_layers=8, PREFILL_LEN=16) — the KV payload is a few KB, so a bandwidth number
there is dominated by fixed overhead and is **not** representative. Sim is for
validating the instrumentation and getting cycle counts; a meaningful GB/s needs
the **device** config (real Qwen3 geometry, dim=2048) or a purpose-built larger
sim config. Sweep `PREFILL_LEN` to separate the fixed (A/C compute) from the
payload-scaling (B wire) components.

### Why the technique makes sense (reasoning)

The TSC is the only clock on the wafer — a per-PE counter, one tick per fabric
cycle; there is no readable "fabric clock". So all on-device timing reduces to
"read this PE's counter before/after". Two guarantees + one hazard follow:
- **Within one PE**, `t_after − t_before` is exact (same monotonic counter) and
  captures compute *and* fabric-wait time. → the segment profiler is trustworthy
  with no correction.
- **Across two PEs**, counters are not zeroed together (each starts at device
  reset; the reset signal reaches PEs at slightly different times), so A-PE `t0`
  vs B-PE `t3` = elapsed time **+ unknown offset**. That offset is what
  reference-correction removes; its magnitude ≈ signal propagation across the PE
  rectangle (tens–hundreds of cycles).

Le's overhead model is correct: cost = **preparation + transfer**, and they are
physically different work. Preparation = on-PE re-layout into the destination's
memory order (`kv_transform` on prefill; the mirror write on decode) — pure
compute, costs cycles with nothing on the fabric. Transfer = the store-and-forward
north shift (wire + small per-hop cost). The profiler separates exactly these.

**Destination handling is only partly "within a PE".** The decode-side *write*
into `XKCache_tile`/`XVCache_tile` is local (preparation on the sink side). But
the *receive* (`@mov16` from the fabric-in DSD) is **wire-coupled** — it blocks on
the shifted wavelets, and store-and-forward means sender and receiver move in
lockstep. So "measure on sender" and "measure on receiver" do not cleanly
compose: the receive overlaps the send.

### ACK round-trip refinement (preferred for the headline number)

To avoid the cross-PE offset entirely, have the sink send a 1-wavelet **ACK** back
after it finishes writing; the sender PE records both `t0` and `t_ack` **on its own
clock** → `RTT = t_ack − t0`, no reference-correction. This is the standard
round-trip trick and is cheap here:

- The seam already reserves **color 22** doing nothing (`build_relay` paints it
  RAMP/RAMP). Repaint it **NORTH→SOUTH** (decode is north, prefill south → ACK
  travels *down* the same seam column).
- A designated **prefill timer PE** (e.g. block column 0, top prefill row) samples
  `t0` at `start_kv_transfer()`, does its own A+B work, then parks on color 22.
- The **last decode PE to finish** (south-most decode row, same column) emits one
  wavelet on color 22 right after `kv_flush_then_init()`; it transits the seam
  south and activates a task on the timer PE, which samples `t_ack`.

Caveats: (1) `RTT = forward delivery + ACK return`; the ACK is one wavelet over a
fixed hop count, so its return is a small **calibratable constant** — measure a
lone no-payload ACK once and subtract (and since payload ≫ 1 wavelet, the error is
small even uncalibrated). (2) The ACK should fire after the *globally* last decode
PE, not just column 0's; all south-row PEs receive the same `Ph` tiles and finish
within a few cycles, so column-0 is a good proxy — gate behind a cheap "all decode
done" reduction if an exact bound is needed.

**Which measurement for which question (complementary, do both):**

| Question | Tool | Cross-PE clock issue |
|---|---|---|
| Total handoff latency → headline GB/s | **ACK round-trip** on one timer PE | none (single clock) |
| Preparation-vs-transfer breakdown | **segment profiler**, per PE | none (within-PE deltas) |
| Sanity cross-check | raw `t0(prefill) − t3(decode)` | small — the two critical PEs straddle the seam ~2 rows apart |

The total is **not** the sum of per-PE segment maxes — the pipeline overlaps prep
and wire across PEs, which is why the ACK gives the real number and the profiler
only explains its composition.

## Phase-1 results (2026-07-06, sim, branch `lexu/staging/kv-transfer-bandwidth`)

Per-PE TSC segment profiler landed (commit `bd21fb3`), guarded by `KV_PROFILE`
(additive; normal path untouched). Ran `test_sim_2x2blk_kv_prof.json` on simfab —
**correctness intact** (`KV-TRANSFER PASS: 4 blocks x 2 layers, bit-exact K+V`;
`SUCCESS: decode top-2 invariant`), 256/256 PEs reporting, max-reduced:

| Segment | cycles | µs | share of sum |
|---|--:|--:|--:|
| **A** prefill gather+transform (states 0–3) | 22,400 | 20.4 | 2.4% |
| **B** prefill north shift (state 4, wire) | 371,443 | 337.7 | 40.6% |
| **C** decode ingress (receive + write) | 521,472 | 474.1 | 57.0% |
| sum A+B+C | 915,315 | 832.1 | — |

**Finding — overturns the earlier "prep-bound at small payload" hypothesis.** Pure
preparation (A) is only ~2.4%; the coupled wire/receive (B + C) is ~98%. The sink
side (C) is the single largest piece, consistent with the south decode row being
the store-and-forward tail (receives the most tiles). So the KV handoff is
**transfer-bound, not compute-bound**, even on this toy config.

**Load-bearing caveat — the sum is a decomposition, NOT the wall-clock latency.**
B (measured on prefill) and C (measured on decode) are the *same* coupled data
movement seen from sender vs receiver, so they run **concurrently**, not in series.
True end-to-end latency ≈ A + (the coupled B/C pipeline, whose tail is C ≈ 474 µs)
≈ ~495 µs, *not* 832 µs. Getting the real number cleanly is exactly what the **ACK
round-trip** phase is for — do not report A+B+C as the transfer time.

**Numbers are overhead-dominated** — 16 KiB over a dim=64 toy, so absolute µs /
0.020 GB/s are not representative; the *ratio* (prep vs transfer) is the signal.
A representative GB/s needs the device config (real dim=2048) and a `PREFILL_LEN`
sweep.

**Toolchain gotcha found (reusable).** This model's `scripts/cslc_bin` wrapper caps
inlined iterations at **8** (deliberate, to bound SRAM on real llama configs), which
makes the CSL `<time>` library's `get_timestamp` (an `inline for`) fail to compile
with `exceeded the maximum of 8 inlined iterations`. Workaround used: read the TSC
registers directly via `@get_config`/`@set_config` (`TIMESTAMP_COUNTER` low-32 +
`PERF_COUNTER_CONTROL`=7 to enable) — same access the library does, no inline loop.
Candidate for its own skill.

## Profiling is DEVICE-ONLY going forward (2026-07-06 directive)

Sim profiling is **abandoned** as a measurement path. A sim `PREFILL_LEN` sweep was
started but **killed mid-run**: e2e sim uses `SimfabConfig(dump_core=True)` and each
run dumps tens–hundreds of GB, so 7 parallel runs filled `/home` (85%→94%). Rule
now: **sim only for small `test_sim_*` toy configs (≤16×16 PEs) as a correctness
check; all profiling / bandwidth runs go on the real CS-3 device** (see project.md
pitfall). No sim bandwidth number was obtained — we go straight to the device
number, which is the more meaningful one anyway (real silicon, real dim=2048).

**Device-egress WIP:** the profiler host readback is currently `read_symbol`
(sim-only). A subagent started a device-compatible stream egress (mirroring the
`is_tsc_pe` TSC-burst-over-output-stream path in `ht_tail.csl`) but was **stopped
incomplete**; its partial work is in git worktree
`.claude/worktrees/agent-a5f7561a999d51c50`. Finishing that egress is the
prerequisite for any device profiling run.

## Device run attempt on CS-3 (2026-07-07) — blocked by egress, env is fine

Device egress built + merged (`e3814ce`): reporter PE per region emits a 4-u32
burst on `kv_prof_out_color` → `src/kv_prof_mux.csl` forwarder → host output
stream; host `runtime.receive`s both. Compiles clean locally (small config,
`--compile-only`, 124 s). Config `test_device_2x2blk_kv_prof.json` = actual size
(dim 2048, 28 layers, 512×512, PREFILL_LEN 256 → **~28 MB** KV, kv_dim_per_pe=4,
max_layers_per_block=7, seq_len_per_pe from PREFILL_LEN/256).

**Outcome: could NOT get a device number.** Findings, in order of certainty:
1. **The device path works.** The **baseline** `test_device_2x2blk_kv` (no profiler)
   ran first try: compile 288.7 s, run 7.0 s, `SUCCESS: decode top-1 invariant`,
   real coordinator `cmaddr=10.27.29.3:9000`. So env / launcher / auth are fine.
2. **The profiler config specifically fails** — 0 successes across ~9 attempts (two
   windows), every one hangs at `Could not find coordinator IP:port` / `Empty
   ingress service url. Falling back to default server: 10.27.24.65:443`. Job logs:
   `wsjob-coordinator-node-name: ""`, `ingress_pes: []` — the ingress/coordinator
   never gets assigned. Baseline NEVER shows this. → my egress's **2 extra host D2H
   streams** (`kv_prof_dec` + `kv_prof_pf`, 3 total with logits) break the device
   ingress-service setup at 512×512. Isolated by the baseline test.
   - **Build-vs-run settled:** the 512×512 profiler config **compiles clean locally**
     (`--compile-only`, 169 s). So it is a **device load/run I/O-setup failure, not a
     build failure.**
   - **The "least overlapping color 0/18" warning is likely a RED HERRING** (Le's
     catch): over-claiming colors is a hard cslc **error**, not a warning — the build
     succeeded, so colors are technically valid. SdkLayout guide §5 (24 colors,
     auto-allocated). No SDK doc found explaining the placer warning or proving
     colors-vs-io_loc; device log only says `Empty ingress service url`.
   - **Better-supported suspects** (SdkLayout guide §7 + [[wse-sdklayout-multistream-io-loc-pinning]]):
     each D2H stream needs a dedicated edge I/O PE; our profiler streams use
     **auto-picked `io_loc` (unpinned)** — multi-stream auto-pick lands on
     invalid/already-used LVDS slots on real HW (sim tolerates it). Also a **separate
     real bug**: host receives use **`nonblock=False`** (`launch.py:3051-3053`) while
     ≥3 streams are active — guide §12.1 requires `nonblock=True` or deadlock.
   - **Implementation map** (annotated with code locations + this diagnosis):
     `assets/prefill-decode-transfer/e2e-profiler-egress.html`.
3. Transient noise on top: CS-3 gateway auth is **intermittent** (`Permission
   denied` / `Connection closed`) — clears on retry-after-~70s (Le's known
   workaround); and there was a real **transient coordinator outage** 07-06 22:19 →
   ~07-07 13:23 that also produced the same fallback message (muddied early
   diagnosis before the baseline isolated it).

**Fix direction (next, deliberate — no more blind wafer runs):** (a) collapse the
profiler egress to a **single** host stream (funnel both reporter bursts through one
mux → one D2H port → 8-u32 combined blob), (b) **pin its `io_loc`** to a known-valid
output LVDS Y (guide/skill), (c) switch host receive to **`nonblock=True`**;
recompile-verify; one device run. Baseline proves ONE extra stream tier works. **CS-3
launch = ONLY `run_device.sh` (SdkLauncher → dispatches to a remote cs_python worker);
`cs_python` is NOT runnable on CS-3 from gala — do not attempt it.**

## Current state

- Mechanism mapped; segments A/B/C **measured in sim** (Phase-1 toy: A=20µs / B=338 /
  C=474µs — transfer-bound). Committed `bd21fb3`. Device egress `e3814ce`.
- Setup floorplan artifact saved (html + pdf).
- **Blocked on:** profiler device egress fails ingress setup at 512×512 (extra
  streams). **Next:** single-stream egress rework → recompile → one CS-3 run for the
  first real GB/s. Then PREFILL_LEN sweep + ACK round-trip.

## Open questions / next actions

- [ ] **Define the measurement window.** Timestamp at: (t0) prefill KV ready =
      entry to `start_kv_transfer()`; (t1) end of segment A (last `kv_transform`);
      (t2) end of segment B (north shift drained at seam); (t3) decode cache
      populated = `kv_flush_then_init` → `kv_init_cont`. Report A=t1−t0, B=t2−t1,
      C=t3−t2, and total=t3−t0.
- [ ] **Instrument with on-device TSC**, following the project's TSC vs host-wall
      methodology (see the cerebras-sdk TSC skills). Watch for the per-pipeline
      TSC plateau artifact; prefer host-wall cross-check.
- [ ] Compute concrete byte totals for the shipped 2×2 configs (fill the TODO
      above) → first effective-GB/s number.
- [ ] Decompose bandwidth: how much of total time is compute (A + C write) vs
      wire (B)? Hypothesis from the code: compute-dominated at small
      `seq_len_per_pe`, wire share grows with prompt length.
- [ ] Compare against the pdSeparate host-DRAM bridge (KV via `kv_handoff.npz`)
      as the alternative transfer path — same metric, both segments counted.

## Work branch

- **`lexu/staging/kv-transfer-bandwidth`** (WaferEngine-staging repo, off
  `main`@`fcfc8c1`) — instrumentation work: Phase-1 segment profiler
  (prep-vs-wire split) then the ACK round-trip. Started 2026-07-06.

## Commands / paths

- Impl: `models/qwen3_1p7b-e2e/` — egress `src/prefill/prefill.csl` +
  `src/prefill/comm_lib/comm_pe.csl`; ingress `src/decode/decode.csl` +
  `src/decode/comm_lib/comm_pe.csl`; seam `src/relay.csl`; layout `launch.py`
  (`build_decode` / `build_relay` / `build_prefill`, `run` geometry ~2757-2812).
- KV-enabled configs: `model_config/test_sim_2x2blk_kv.json`,
  `test_sim_1x2blk_kv.json`, `test_device_2x2blk_kv.json`.
- Run sim: `cd models/qwen3_1p7b-e2e && ./run_sim.sh model_config/test_sim_2x2blk_kv.json`
- Setup viz: `projects/WaferEngine-staging/assets/prefill-decode-transfer/`

## Last updated

2026-07-06 — topic started; reading summary + setup artifact recorded. Measurement
design added (TSC `<time>` per-PE, 1.1 GHz, segment-profiler for compute-vs-wire
split, cross-PE ref-correction for headline GB/s; sim-first via read_symbol). Skill
`cerebras-sdk-pe-timestamp-timing` updated (freq fix + segment profiler). No numbers
yet — next: instrument `prefill.csl`/`decode.csl` and run the sim.

2026-07-06 (cont.) — added the reasoning (why per-PE TSC + segment profiler is
sound; prep-vs-transfer; destination receive is wire-coupled) and the **ACK
round-trip** refinement (repaint seam color 22 NORTH→SOUTH, sink ACKs the timer PE
→ single-clock RTT), now preferred over cross-PE ref-correction for the headline
GB/s. Profiler is complementary (breakdown only).

2026-07-06 (cont.) — **Phase-1 profiler implemented + run in sim** on branch
`lexu/staging/kv-transfer-bandwidth` (commit `bd21fb3`). Result: A=20µs (prep, 2.4%),
B=338µs, C=474µs — transfer-bound, not prep-bound; A+B+C is a decomposition not the
true latency (B/C overlap). Fixed byte math (max_layers_per_block=2 → 16 KiB) and
recorded the cslc-wrapper inline-cap gotcha. Next: ACK round-trip + device config.
