# ht_head.csl — vocab-rotation embedding LUT

> Kernel algorithm walkthrough. Model `qwen3_1p7b-prefill`, ref config `test_sim_2x4_kv_varlen.json`.
> Diagram: `qwen3_1p7b-prefill.ht_head.svg`. Comms taxonomy per the `cerebras-kernel-comm-patterns` skill.

## Core idea — rotate the vocab, don't route on the key

Turns token ids into embedding rows `W_E[token_id]`. `W_E` is `[vocab, dim]`, too big for one PE, so it is
sharded across the HEAD band. The problem: a column owns some tokens, but their embedding rows may live on
**other** columns' vocab shards. The fabric **cannot route by token-id** (no destination field, comptime
colors, no keyed crossbar — skill Gate 1). So instead of routing each token to its shard, the kernel
**rotates every vocab shard past every column in a ring**; at each step each PE locally checks whether any of
its tokens fall in the vocab range it currently holds (`compare_record`) and copies that row. After
`HEAD_WIDTH` steps every token has seen every shard → all resolved. This is Gate 1's lawful escape #1
(*replicate/rotate the data, don't route on a key*).

## Data distribution on PEs

HEAD band = **HEAD_WIDTH columns (X) × dim rows (Y)** (2×4 config: 4×8).

| Tensor | Sharding | Notes |
|---|---|---|
| `we_buf` (W_E shard) | vocab on **X**, dim on **Y** | column `local_px` owns vocab rows `[local_px·V_per_pe, +V_per_pe)`; each Y-row owns `dim_per_pe` features → a `[V_per_pe, dim_per_pe]` tile. |
| `token_id_buf` | each column owns its `2·reduce_len` seq tokens, **replicated on Y** | one head column feeds 2 block columns; Y-replication lets each dim-shard PE copy its own slice. |
| `X_tile` (output) | chunk-major `[chunk][2 bcol][dim_per_pe][reduce_len]` | the embedded hidden state, waiting to hand east into block0. |

`we_buf[WE_LEN]` carries a **self-describing origin-column tag** (`chunk_col`, set in `init`): as the tile
rotates, `compare_record` reads the tag to know which vocab range it currently holds — no hop counting.

## Communications + which task owns each step

**Phase 0 · ingest (P-2 router multicast + G-2 FIFO peel)**
- `ingress` — peel the metainfo header off the front of the `tok_bcast` stream (N multicast from demux).
- `ingress_ids` — decode `request_n_chunks`/`last_token_chunk_pos`/`start_chunk`, pack the fp16 tail, drain
  the column's token ids into `token_id_buf`; `@activate(init)`.

**Phase 1 · embed via rotation (cyclic-shift ring + local LUT match)**
- `init` — compute `local_px`, tag `we_buf_0`, run **step 0** `compare_record`; branch on `P_BLOCK_SIZE`
  (`>1` → `launch_shift`; `==1` single column owns whole vocab → straight to handoff).
- `compare_record` — pure local LUT match: for each token in range of the currently-held vocab tile, copy
  its embedding row into `X_tile`. No comms.
- `launch_shift` — one ring hop: send current tile (+tag) on `y_send`, receive next on `y_recv` (two disjoint
  microthreads run concurrently).
- `shift_done` — `compare_record` the newly-arrived tile (hops `0..P-2`; the P-th "restoring" hop just rolls
  `we_buf` back to origin), swap ping-pong pointers, `launch_shift` again or (after `HEAD_WIDTH` hops)
  `@activate(forward)`.

**Phase 2 · concat east into block0 (G-1 parity chain + G-2 FIFO peel)**
- `forward` — forward upstream columns' chunk payloads from the west (FIFO peel, `my_local_px·chunk_own_len`).
- `send_own` — emit this column's own chunk east; chunk 0 assembles `[bcol0][meta][bcol1][meta]` with the
  metainfo tail.
- `handoff_done` — `current_prefill_chunk++`; more chunks → re-arm `forward` (per-chunk loop); request done →
  reset counters, `@activate(ingress)` (per-request loop). block0's re-arm backpressures this send.

## Communication summary

| Movement | color / queue | direction | pattern | task(s) |
|---|---|---|---|---|
| token+meta ingest | `tok_bcast` / q3 | N multicast | **P-2 multicast + G-2 peel** | ingress / ingress_ids |
| vocab rotation ring | `y_send`·`y_recv` / q2 | X ring (2-hop) | **cyclic-shift ring** (Cannon-style operand shift) | launch_shift / shift_done |
| concat east | `x_src` q4 / `x_dst` q3 | X east | **G-1 parity chain + G-2 peel**; into block0 = **P-6 p2p** | forward / send_own |

Correctness = **count-exactness** (both ends compute the same wavelet count from coords / `local_px` /
`request_n_chunks`); a mismatch is a silent hang. This is why widening the metainfo header must be applied
consistently on every reader.

## One line

Same program on every PE; `local_px` gives each PE a different vocab shard + different tokens; `P_BLOCK_SIZE`
is the shared ring size (steps + the 1-column skip). A keyed embedding scatter becomes a static ring rotation
plus local matching — the standard way to do a keyed lookup on the wafer.
