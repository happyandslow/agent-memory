---
summary: M2-S1 — fixing the three broken measurement lenses in the pdSeparate launcher, measuring the KV host→device uplink for the first time (1.85x slower than the downlink that had proxied for it), and the placement/tooling lessons that made it a zero-perturbation measurement.
tags: [waferengine-staging, m2, pdseparate, measurement, timing, bandwidth, sdklayout, io_loc, cs3-cluster, provenance]
---

# M2-S1 — measurement lenses, and the uplink nobody had timed

Session 2026-07-29→30. Snapshot **`a3a509c`** + S1 changes, branch
`lexu/staging/m2-benchmark`, worktree `/home/lexu/we-m2bench`. Real WSE-3 on EPCC CS-3.

> **Plan and state live in the durable docs, which win on any conflict:**
> `milestones/M2-tiering-cost-model.md` and `milestones/M2-timer-provenance.md` §9.
> This file keeps only the incidental learnings. Related:
> [[m2-s0-baseline-and-timer-provenance]], [[h2d-host-device-bandwidth]],
> [[prefill-decode-transfer-bandwidth]], [[e2e-pdSeparate-device-validation]].

## The result worth remembering

**The host KV path is asymmetric and the slow direction is the one the cost model needs.**
Measured on-device (TSC on the band-0 `kv_ingress_adaptor`): H2D ingress **0.7726 GB/s
aggregate / 0.1931 GB/s per stream**, against the D2H egress's 1.426 / 0.357 — **1.85×
slower**. And that *understates* it: egress is host wall clock, ingress is device TSC, and TSC
reads shorter than host-wall for the same transfer.

Every "reload from host" figure written before this measurement had divided by the **downlink**
rate, as a stand-in for a direction nobody had timed. At `L = 8192` the reload lane moves
**753 → 1390 ms**.

*General shape:* when a cost model needs direction A and only direction B has been measured,
the substitution is invisible in the arithmetic. Label the direction in the units, not just the
prose.

## Timing a host transfer without perturbing it

The host-side way to time an H2D transfer is to `task_wait` on the `nonblock` send handles —
but that fences the host against the device and changes the run. The device-side way does not:

- **Find the funnel PE.** Per band, every wavelet passes through exactly one PE — the
  `kv_ingress_adaptor` (1×1). Downstream, each injector PE handles one row-slice and each block
  column only its own row, so nothing else sees a whole band.
- **Single-PE span, one counter.** Start on the round's first arrival (guarded on `row_idx == 0`
  — the task fires once per *row*, 256× a round), end when the last segment is relayed.
  Cross-PE TSC differences are meaningless; a single PE's `end - start` is not.
- **Reuse the existing burst format.** Copying `ht_tail.csl`'s 8×u32 layout (slots 0–2 start,
  4–6 end, 3/7 pad) meant the host reused `_unpack_tsc` verbatim — no new packing code, so no
  new packing bug. 8 is even, which the output port requires (SDK 1.13.2).
- **Cost: nothing.** `trace_sha256` identical to the baseline; zero of 91 device-classified
  leaves moved beyond 0.05%.

## `io_loc` is a routing decision, not a free-slot lottery

The first attempt pinned the timer's host port at the **west** edge, because every other stream
in the model does. It re-routed **three of the four KV ingress buses**.

- A host stream is `host → a 1-PE region at io_loc → your port` (`create_input_stream(port,
  io_loc, io_buffer_size=1024)`; **no colour parameter — the colour is the placer's**). The
  fabric-crossing part is a "bus", and the placer **re-solves globally** whenever one is added.
- The damage was not the 645-column traverse — that ran along row 0, which is empty fabric
  (every region starts at `y=1`). It was the **x=0 column**, which passes *through* the other
  six io_port 1-PE regions; two of them already held the colour the new bus wanted, forcing a
  mid-route colour switch (`c18 → c19 → c18`) and a global re-solve.
- **`fabric.json` lists LVDS on BOTH edges** — `ingress_connections` / `egress_connections` are
  124 entries each: 62 at `x=0` **and 62 at `x=761`** (`y = 18k` in, `18k+1` out). Nothing in
  this model had ever used the east edge, and the `io_loc`-pinning skill only documented x=0.
- Moving to the **east** edge next to the source PE gave `(645,0) → (761,0) → (761,1)`: 116
  columns of empty fabric, **zero existing regions traversed**, no router warning, and **6/6**
  pre-existing buses byte-identical to the baseline.

**Rule: pick the edge nearest the source PE, and read `fabric.json` rather than assuming the
edge other code happens to use is the only one.**

## Reading the compile artifacts

`<store>/<phase>/` carries four files worth knowing, all cheap to inspect and far more
informative than the compile log:

| file | what it answers |
|---|---|
| `sim_port_map.json` | `lvds_ports` = the pins actually claimed (`color` here is an **ordinal**, not a fabric colour); `buses` = port names ↔ lvds ids |
| `colors.json` | every named colour → its fabric id. **Per-region occupancy is the real scarcity measure** |
| `plan.json` | `data.buses[].routes[].wires[].pts` = the **actual route**, `c@(x,y)` per hop. This is how you find out where a bus really goes |
| `fabric.json` | `fabric_dimensions`, `max_pos`, and the full LVDS connection lists for both edges |

**"All 24 colours are in use" is not scarcity.** 149 named colours map onto 24 ids because the
same id is deliberately reused across spatially disjoint regions (`row_0..row_3:kpipe_color_a_4`
are all id 10). The real measure is **per region**: here the block rows use **21–22 of 24**, so
only `{0, 18}` are free in all four — which is why any bus that must cross the block region
lands on one of those two, and why the three KV ingress buses that do cross were the ones the
router warned about while band 0 (whose adaptor sits on empty row 0) never did.

## Two ways a number gets a false pedigree

**A tolerance quoted for headline fields does not transfer to every field.** The baseline
reported "every device field reproduces to ≤0.02%" — true of its three anchors. Diffing the
baseline's *own two runs* (bit-identical output, so all difference is jitter) shows **64 device
leaves differing by up to 0.0268%**. A 0.02% whole-file gate would have failed a good run.
**Calibrate a tolerance against the baseline's own run-to-run spread**, and say so where the
tolerance is written down.

**A field whose value mixes two scopes cannot be rescued by renaming.** `prefill_device.tsc`
had `prefill_len` = round 0's prompt length and `tok_per_s` = that divided by **round 7's**
span — a **+42.8%** artifact (527.1 vs the correct 369.0), worse than the scope error the
session came to fix and never previously quantified. A field that describes one round gets a
`last_round` name; a field that divides one round by another gets **deleted**, with a pointer to
the per-round field that is correct. The in-source comment had documented the numerator
("throughput divides by the prompt length") and said nothing about the denominator having moved
on — correct sentence, wrong number.

## A "free lever" that does not exist

S0 had flagged `KV_NPZ_DIR` (implemented at `launch.py:96-107`, never exercised) as *the cheapest
route to the physical floor of the host KV round trip*: point it at `/dev/shm/<run>` and the whole
prefill→decode npz handoff moves to tmpfs. **It does not work on this appliance.** The run wrote
exactly one file —

```
[prefill] KV egress round 0 saved: /dev/shm/m2s1b_kvnpz/kv_egress_0.npz
... np.savez ... OSError: [Errno 28] No space left on device
```

— and died on the next request. Each per-request KV npz is ~32 MB; a Kubernetes pod's `/dev/shm`
defaults to **64 MB**, so it holds one and not two. Worst part: it fails **mid-run**, after a wafer
allocation, a 6 GB store upload and a full prefill round — not at startup, where a size check would
have cost nothing.

*General shape: an implemented-but-never-exercised lever is not a known-good lever. Cost of finding
out here was a 20-minute build plus a 10-minute run.* The physical floor of the host round trip is
still unmeasured.

## Operational notes

- **The freshness gate hashes the launchers and the model config, not just the CSL.**
  `_fingerprint_rel_files` covers `launch*.py`, `src/{prefill,decode}/**`, `host/*.py` **and
  `model_config/<mc>.json`**, and `--mode reload` hard-exits on a mismatch. So "this change is
  host-side, the store stays valid" is false — the store stays valid, the *gate* does not.
  Corollary: two **serve-time-only** keys (`KV_SEND_FENCE`, `KV_NPZ_DIR`) living in that config
  force a whole separate store to vary them, even though neither enters the layout.
- **`--mode compile --build-phase decode` is a 4.5-minute iteration gate.** cslc is 51 s; the
  ~40 min figure is dominated by prefill (420 s) plus two 4 GB weight stagings. Compile, then
  diff `plan.json` / `colors.json` against the baseline store — that catches placement damage
  before spending a serve run.
- **Chain long jobs server-side.** A `setsid nohup` watcher that polls its predecessor's log and
  launches the next stage survives ssh loss entirely; the local session only has to read a log.
- SSH: automation must use the **`CS-3-cmd`** alias, never `CS-3` — see
  [[cs3-device-run-flakiness-and-safe-cancel]] (auto-memory) for the protocol and the failure
  signatures.

## Loose end recorded, deliberately not acted on

`fabric.json` reports **`core_frequency: 750000000.0`** (0.75 GHz) for this appliance, a *third*
value against the pdSeparate line's 0.85 GHz and the `kv-feature` line's 1.1 GHz. If the TSC
ticks on the core clock, every device time here is high by 13% and `kv-feature`'s by 47%; ratios
within a line survive, absolutes do not. **Le's call: the current conversion is deliberate —
record it, change nothing.** The cheap test rides along with a future device run: bracket a
host-blocking round trip on-device and see which divisor reconciles TSC with `perf_counter`.
