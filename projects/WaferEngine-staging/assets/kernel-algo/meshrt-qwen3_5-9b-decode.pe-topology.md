# MeshRT Qwen3.5-9B decode PE topology

Repository state: `CongjieHe/WaferEngine`, branch `meshrt`, commit
`5d47163b6586824a9fce5ff045bff67d9f0f6552`.

## Scope caveat

`Qwen3_5-9b-decode` is a component performance model. `HT_head`, `layer_block`,
and `HT_tail` are compiled and measured as independent layouts. The result JSON
composes their TSC cycles for 24 GDN and 8 Full layers on two wafers. The repo
does not contain a single layout that places these three artifacts together, nor
an exact layer-to-wafer placement map.

## Layer artifact geometry

| Batch | Compute region | group-16 phase-2 root | Per-PE `HX` / `H` / `F` / `KV` | KV positions per X column |
|---|---:|---:|---:|---:|
| 1, 2 | 256 × 256 | (136, 136) | 16 / 16 / 48 / 4 | 18 |
| 4, 8 | 512 × 512 | (264, 264) | 8 / 8 / 24 / 2 | 9 |

All compute PEs run the same `decode_main_task`. The task first benchmarks the
Full Attention path for 16 warmup plus 256 measured steps, resets phase-disjoint
state, then benchmarks the GDN path. The Full and GDN timings therefore do not
represent two spatially separate PE regions.

## Data distribution

- X columns shard the residual/input hidden dimension (`HX`) and round-robin KV
  sequence positions (`position mod logical_mesh_width`).
- Y rows shard mixer/FFN features (`H`, `F`) and Full/GDN head features (`KV`,
  `GQ`).
- Full KV-head bands, GDN QK-head bands, and GDN value-head bands are scoped
  contiguous spans of Y rows within every X column.
- GDN recurrence also shards its 128-wide key dimension over the first 128 X
  identities; at P greater than 128, `local_x / 128` selects a value chunk.

## PE roles and communication

- Every compute PE performs local GEMVs, pointwise operations, and owns local
  weight/state shards.
- For full-axis collectives, phase-1 roots repeat at coordinate
  `coordinate mod 16 == 8`. Phase-2 combines those group roots at coordinate 136
  (P=256) or 264 (P=512). The result is router-multicast back along that same
  axis: P-1 plus P-2.
- Scoped Y collectives use a single chain to the midpoint of each head band,
  followed by multicast. At P=256: Full KV roots are `32 + 64k`, GDN QK roots
  are `8 + 16k`, and GDN value roots are `4 + 8k`.
- The intersection of the phase-2 X-root column and Y-root row is the Layer
  timing/result PE.
- A 1×P control-demux strip sits west of the compute grid. Host start records
  enter from the bottom, are peeled south-to-north, and one record is multicast
  west-to-east across each compute row.
- A 1×P result-mux strip sits east. Only its PE on the timing-root row receives
  the result packet; routing carries that packet to the bottom host port.

## Layer execution domains

Full Attention uses X reductions for input projection, global score max and
score/value output; scoped Y bands for per-KV-head Q/K and score work; Y
reductions for output projection; then X and Y reductions for FFN up/down.

GDN uses an X reduction for projection, scoped Y bands for QK and value-head
work, X reductions for recurrence contractions, a Y reduction for output, then
the same FFN. Colors 0–4 are synchronously repainted between these domains.

Editable source: `meshrt-qwen3_5-9b-decode.pe-topology.excalidraw`.
Derived previews: `meshrt-qwen3_5-9b-decode.pe-topology.svg` and
`meshrt-qwen3_5-9b-decode.pe-topology.png`.
