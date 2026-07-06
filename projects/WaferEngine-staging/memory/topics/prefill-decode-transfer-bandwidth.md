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

This equals the raw model KV footprint (padding-free for these configs):
`bytes = n_layers · bsz · (n_kv_heads · head_dim) · PREFILL_LEN · 2(K,V) · 2(bf16)`.

**Concrete values** (resolved 2026-07-06 for the pdSeparate handoff; same total KV
volume applies to the e2e seam):

| Config | geometry | per-direction KV |
|---|---|---|
| `test_device_2x2blk_kv` | n_layers=28, bsz=1, n_kv_heads=8, head_dim=128, PREFILL_LEN=2048 | **224 MiB** (58,720,256 u32) |
| `test_sim_2x2blk_kv` | n_layers=8, bsz=1, n_kv_heads=2, head_dim=16, PREFILL_LEN=16 | **16 KiB** (4,096 u32) |

(Device: `per_pe_u32 = max_layers_per_block·kv_dim_per_pe·reduce_len = 7·4·8 = 224`;
`Ph·Pw·per_pe_u32 = 512·512·224`. Cross-check `28·1·1024·2048·2·2 = 234,881,024 B`.)

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

## Updates — 2026-07-06 · pdSeparate host-bridge + measurement design

The two models take opposite transfer paths, both in scope for this topic:
- **e2e** — on-chip: gather+transform then north shift through the relay seam
  (segments A/B/C above). Timing needs *in-kernel* TSC.
- **pdSeparate** — host-bridge: prefill D2H → host re-layout → decode H2D, two
  separate device artifacts, KV serialized to an ephemeral `kv_handoff.npz`. This
  maps almost 1:1 onto the SDK `bandwidth-test` methodology, so it is the easier
  first measurement. **pdSeparate is the target of the plan below.**

### pdSeparate handoff — 5 stages (all anchors in `models/qwen3_1p7b-e2e-pdSeparate/launch.py`)

| Stage | What | Where | Cost type |
|---|---|---|---|
| **S1 D2H wire** | prefill KV egress: switch-gather → mux PE → host, direct output stream `kv_egress_stream` (`memcpy_required=False`) | `runtime.receive(...)` **line 3410** (`nonblock=False`); bytes `= n_egr*4`, `n_egr` @ 3408 | fabric/PCIe wire |
| **S2 prefill transform** | `_parse_kv_egress` (3411) + `_extract_transform_kv` (3243–3283): unpack, PE-grid transpose (decode mirror `(lx,ly)←(ly,lx)`), V in-tile transpose, seq zero-pad to `MAX_SEQ_LEN/P` | host CPU (numpy) | transform/compute |
| **S3 bridge (artifact)** | `np.savez` → `kv_handoff.npz` (3424) + subprocess teardown/startup + `np.load` (3627) | disk + process fork | **sim-harness artifact** |
| **S4 decode transform** | `_repack_kv_stream` (3496 / 3286–3327): seq truncate to `PREFILL_LEN/P`, demux reorder, pack 2×fp16→u32 | host CPU (numpy) | transform/compute |
| **S5 H2D wire** | decode KV ingress: host → `kv_adaptor`→`kv_demux`→north-shift, direct input stream `kv_stream` | `runtime.send(...)` **line 3498** (`nonblock=False`); bytes `= kv_stream_data.nbytes` | fabric/PCIe wire |

Payload each direction = the KV volume table above (224 MiB device / 16 KiB sim).

### The three bandwidth numbers to report

- **Wire bandwidth** (pure fabric/PCIe) = `bytes / (S1 + S5)`.
- **Handoff bandwidth** (transfer **+** transform — *this is Le's ask*) =
  `bytes / (S1 + S2 + S4 + S5)`. Excludes S3.
- **Full end-to-end** (informational) = `bytes / (S1+S2+S3+S4+S5)`.

### Method — two tiers

**Tier 1 — host wall-clock (do first, ~10 lines, no kernel edits).** Bracket
`time.perf_counter()` around S1, S2, S4, S5 (and S3 separately). Valid here
*because* the stream calls are `nonblock=False` — they block to completion, so
wall time = drain/fill time (unlike the aggregated-`nonblock` case
`bandwidth-test` warns about). Host time is in real seconds → sidesteps the clock
question. See [[cerebras-sdk-tsc-vs-hostwall-diagnostic]].

**Tier 2 — on-device TSC (rigorous wire number).** Both streams are SdkLayout
direct streams, so apply [[cerebras-sdk-pe-timestamp-timing]] (base API +
sync/tic/toc) with [[cerebras-sdk-direct-stream-tsc-sync-tic-toc]] (the
direct-stream port + the `nonblock=False`-on-toc drain trick). Put tic/toc on the
egress mux PE and the ingress adaptor/demux. Cross-check vs Tier-1 (agree within
~30% or investigate).

### Caveats (load-bearing)

1. **Clock constant is contested.** pdSeparate's decode TSC uses **1.1 GHz**
   (`launch.py:3125` `per_tok_sec = per_tok_cyc / 1.1e9`); the SDK
   `bandwidth-test/run.py` uses **0.85 GHz**. A wrong clock scales bandwidth
   linearly (~30% here). Use the repo's **1.1 GHz** for consistency with its
   existing tok/s numbers, but validate against a known-duration anchor.
2. **Sim timing is not physical.** simfab bandwidth is meaningless; the real
   number needs a **CS-3 device run** of `test_device_2x2blk_kv` (224 MiB). But
   pdSeparate currently **fails to compile on device** (prefill SRAM overflow at
   `PREFILL_LEN=2048`, see [[e2e-pdSeparate-device-validation]]) → must drop
   `PREFILL_LEN ≤ ~512` first, or measure host-transform anywhere + wire on a
   smaller device config.
3. **S3 is a simulator artifact, not fundamental.** The `.npz`-to-disk + subprocess
   fork exists only because simfab allows one Simfabric per OS process. Real
   PD-disaggregated serving moves KV device→interconnect→device with no `/tmp`
   file. Count S3 separately; keep it out of the "handoff bandwidth" number.

### Next actions (pdSeparate)

- [ ] Add Tier-1 `perf_counter` brackets at S1/S2/S4/S5 + payload byte prints;
      run `test_sim_2x2blk_kv` → first per-stage split (relative, not absolute BW).
- [ ] Get a device-viable config (PREFILL_LEN ≤ 512) compiling → real S1/S5 wire BW.
- [ ] Tier-2 TSC on the mux/demux PEs; reconcile 1.1 vs 0.85 GHz against Tier-1.
- [ ] Compare handoff BW: pdSeparate host-bridge vs e2e on-chip seam, same metric.

Related skill created this session: [[cerebras-sdk-pe-timestamp-timing]] (WSE PE
`<time>`/TSC how-to, distilled from the SDK `bandwidth-test` reference).

## Last updated

2026-07-06 — added pdSeparate 5-stage handoff map, concrete KV byte totals
(224 MiB device / 16 KiB sim), 2-tier measurement plan (host-wall first, TSC
second), and the 1.1-vs-0.85 GHz clock caveat. Instrumentation not yet applied.
