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

## Current state

- Mechanism fully mapped from source; segments A/B/C identified with code anchors.
- Setup floorplan artifact saved (html + pdf).
- **No timing instrumentation yet.** The existing e2e device run reports overall
  `run 6.9s` and decode throughput (2240 tok/s) but does **not** isolate the KV
  handoff cost ([[e2e-pdSeparate-device-validation]]).

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

2026-07-06 — topic started; reading summary + setup artifact recorded, measurement
plan drafted. No numbers yet.
