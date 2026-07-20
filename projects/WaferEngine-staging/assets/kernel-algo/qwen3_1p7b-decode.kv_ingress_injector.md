# kv_ingress_injector.csl — KV-cache ingress switch column (host → block, WEST scatter)

> Kernel algorithm walkthrough. Model `qwen3_1p7b-decode`, ref config `test_sim_2x2block_kv_varlen.json`
> (`Pw=16`, `P_BLOCK_SIZE=8`, `P_Y_BLOCK_NUM=2` bands, `bsz=2`, `n_layers=7` → `max_layers_per_block=2`,
> `KV_DSD_SEG_MAX=100` forcing real segmentation).
> Diagram: `qwen3_1p7b-decode.kv_ingress_injector.svg`. Comms taxonomy per `cerebras-kernel-comm-patterns`.
>
> **State documented: the CURRENT WORKING TREE of branch `lexu/staging/s6a-inner-pe-kv-route-a`
> (uncommitted S6a work on top of `fcfc8c1`).** Two things here are *not* at `fcfc8c1`: the per-round
> meta tile widened `KV_META_LEN 2 → 4`, and the `n_segs_rt == 0` retain-heartbeat fast-path in
> `emit_scatter` (`kv_ingress_injector.csl:98-106`). Both are described below as current.

## Core idea — a vertical switch column that hands row `ly` to injector PE `ly`, then scatters it WEST

This is the **mirror image** of prefill's `kv_egress_colmux` (`kv_ingress_injector.csl:3-5`). Egress
gathers rows EAST and drains them NORTH to a D2H stream; ingress takes an H2D stream in at the TOP
edge and pushes it SOUTH down a `1 × P_BLOCK_SIZE` column, dropping one row-slice off at each PE,
each of which scatters its slice **WEST** into the decode block's east edge.

The column is a **P-4 seam / switch gather-scatter**. Injector PE `ly` starts with its switch at
**pos0** (`NORTH→RAMP`, take my row); the adaptor one PE north emits a `SWITCH_ADV` control wavelet
after each row, flipping PE `ly` to **pos1** (`NORTH→SOUTH`, forward), so row `ly+1` threads past it
**at the router** and is never buffered (`:7-13`, `launch.py:1493-1495`). Peak memory per injector PE
is two 1-word buffers (`:51, 66`) — no store-and-forward.

KV is fp16 riding **2-per-u32**, and this PE never reads the values: everything moves as whole 32-bit
wavelets via `@mov32` (`:15-17`). Counts are therefore in **wavelets**, not fp16.

## Data distribution on PEs

Per band `by` (one per `P_Y_BLOCK_NUM` block-row), placed in the free column **east** of the block,
staircase-offset by `by` (`launch.py:1470, 1476-1478, 1484, 1509, 1541`; `STAIR_X0 = PLACE_X + Pw + 1`,
the `+1` past decode's east strip that prefill lacks):

| Element | Placement (2×2 config) | Role |
|---|---|---|
| host H2D stream `by` | TOP edge above column `STAIR_X0+by` | one input stream per band (NS = 2) |
| `kv_ingress_adaptor` | 1×1 at `(STAIR_X0+by, y0-1)` | peel meta[0], relay rows SOUTH, emit `SWITCH_ADV` |
| **injector** (this kernel) | 1 col × `P_BLOCK_SIZE`=8 at `(STAIR_X0+by, y0)` | switch demux: take row `ly`, scatter WEST |
| `kv_fwd` extender | `by` cols × 8 at `(STAIR_X0, y0)` (none for `by=0`) | transparent E→W relay over the staircase gap |
| decode block `by` | `Pw`×`P_BLOCK_SIZE` = 16×8 at `(PLACE_X, y0)` | receives at its east edge, west-shifts across columns |

The injector holds **no KV**: `meta0_buf` (1 u32) and `sync_buf` (1 u32) are its entire data footprint
(`:51-52, 66-67`). Everything else is `fabin → fabout`.

**Gate 0 note.** Nothing here is a collective. The KV cache is sharded **by absolute position round-robin
across the block's `P_BLOCK_SIZE` rows** — injector PE `ly` owns exactly the rows the block row `ly`
will hold — so the movement is a **static permutation** (host packs row-outer in `_repack_kv_band`,
`launch.py:2434-2482`), fully determined by `ly`. Gate 1 passes trivially: no runtime key is routed on;
the only runtime quantity is a **segment count**.

## The metadata tile — what it carries, who peels which word (S6a widening)

Each row-slice on the wire is `[ num_cols metainfo u32 | KV ]`. The metainfo block is **one tile per
block column**, so the block's west-shift can peel one per column (`:26-30`, `decode.csl:1571-1581`).

**The S6a change: `KV_META_LEN` went 2 → 4 i16** (`launch.py:1413`, `decode.csl:1562`):

```
per-column meta tile = 4 × i16 = 2 × u32
  i16 slot 0: plen           = prefill_len_per_pe   this round  ─┐ packed into u32 #0
  i16 slot 1: decode_len     = decode_len_per_pe    this round  ─┘  (low16 | high16)
  i16 slot 2: retained_len   = retained_len_per_pe  this round  ─┐ packed into u32 #1
  i16 slot 3: pad (0)                                           ─┘
```
Host packing: `meta_tile = np.array([plen, dlen, rlen, 0], dtype=np.int16).view(np.uint16)`
(`launch.py:2459`), replicated `Pw` times per row (`launch.py:2467-2468`).

**What the widening changed, concretely** — `num_cols` is passed as `Pw * KV_META_LEN // 2`
(`launch.py:1487, 1524`), i.e. the meta block **in u32**:

| | at `fcfc8c1` (`KV_META_LEN=2`) | **now** (`KV_META_LEN=4`) |
|---|---|---|
| `num_cols` param | `Pw` = 16 u32 | **`2·Pw` = 32 u32** |
| `metablk_in/scatter_dsd` extent (`:55-56`) | `num_cols-1` = 15 | **31** |
| per-row wavelets | `Pw + C_kv·plen` | **`2·Pw + C_kv·plen`** (`launch.py:2540`) |
| meta words the injector *reads* | 1 (u32 #0, low 16) | 1 — **unchanged** |

**Who reads what.** The injector peels **only u32 #0 of column 0** and reads **only its low 16 bits**:
`n_segs_rt = D_kv * @as(u16, meta0_buf[0])` (`:85`) — the `@as(u16, u32)` truncation keeps `plen` and
discards `decode_len` in the high half, which is *why* the widening needed no change here. `retained_len`
lives in u32 #1 and the injector never looks at it; it rides through inside the `num_cols-1` block.

**The peel is wavelet-count-neutral** (`:31`): the injector consumes u32 #0 into memory and then
**re-emits it** (`scatter_meta`, `:87`) before forwarding the remaining `num_cols-1`, so the block
downstream still receives the full `num_cols` metas. The switch stays at **pos0 for the entire row**
— peel, both meta ops, and every KV segment — because the adaptor only `SWITCH_ADV`s *between* rows
(`:29-31, 96-97`).

**`retain_rt` is derived on-device, never transmitted.** There is no retain flag on the wire. Each
decode block PE computes `retain_rt = @as(i16, prefill_len_per_pe_rt == 0)` (`decode.csl:1580`) after
peeling its own meta copy, and skips the whole per-layer K/V ingest when it is set
(`decode.csl:1647-1653`); `round_reset` then keeps the existing cursor instead of resetting it
(`decode.csl:290`, `iter_num_bank[li] = retained_len_per_pe_rt` at `:305`). This is the
**replicate-the-decision, don't route on it** escape from Gate 1 — every PE derives the same bit from a
tile it already receives, so the branch stays static and no keyed routing is needed.

## The retain heartbeat and the `n_segs_rt == 0` fast-path (the subtle part)

A **retain round** sends `plen == 0`: a **meta-only heartbeat**, `num_cols` metas and **zero KV payload**.
The metas still carry `decode_len` and `retained_len`, which is exactly the point — the block must learn
this round's budget and cursor without re-receiving any KV.

`plen == 0` ⇒ `n_segs_rt = D_kv * 0 = 0`. **Before the fix**, `emit_scatter` fell straight into
`seg_idx += 1; if (seg_idx < n_segs_rt)` — `1 < 0` is false — and so ran the *else* branch, executing
**one unconditional `@mov32(scatter_dsd, seg_in_dsd)` of `seg_len` wavelets** even though the round
carried none. Two failures compounded:

1. a **phantom `seg_len` read** on the ingress color that the host never sent, and
2. the next round's wavelets partly consumed as if they were this round's segment, leaving
   **undrained wavelets on the ingress color** at the round boundary.

Because decode's per-round teardown *rebinds* IQ7/OQ7 from the ingress colors back to broadcast
(`decode.csl:1654` `kv_ingress_flush_then_resume`, barrier at `:310-312`), and **a queue can only be
rebound after it is drained**, residue on that color turned into the observed **round-1 IQ7 remap
FATAL** — not a hang, an outright remap failure, because the rebind ran against a non-empty queue.

**The fix** (`:98-106`, and its twin in the adaptor at `kv_ingress_adaptor.csl:82-92`) is a fast-path
that skips the segment move entirely and jumps straight to the round-sync step:

```csl
if(n_segs_rt == 0) {
    seg_idx = 0;
    if(is_col_tail == 1) { @activate(sync_src_id); }
    else                 { @activate(sync_wait_id); }
    return;
}
```

The invariant it preserves: **the switch still advances and the round-sync barrier still fires exactly
once per row**, so the column's re-arm bookkeeping is identical whether the round carried KV or not.
Only the data move is elided. Count-exactness holds because *both* ends now compute `n_segs_rt = 0`
from the same peeled `plen` — the adaptor's matching fast-path is what keeps the sender from emitting
the phantom segment in the first place.

## Communications + which task owns each step

**Ingest (from the adaptor, one PE north):** `in_color` (region-allocated `inj.color("in_color")`,
`launch.py:1488`) on **IQ2**, switch-painted `[pos0: N→RAMP, pos1: N→SOUTH]` (`launch.py:1493-1495`),
entering via a TOP-edge input port connected to the adaptor's BOTTOM output port
(`launch.py:1512-1517, 1543`).

**Phase A · peel + re-emit the meta block** (switch held at pos0)
- `peel_meta0` (task 12, `:80-82`) — `@mov32` peels u32 #0 (extent 1) into `meta0_buf`,
  `→ scatter_meta`.
- `scatter_meta` (task 13, `:84-88`) — latch `n_segs_rt = D_kv * @as(u16, meta0_buf[0])`, reset
  `seg_idx`, then **re-emit** the peeled word WEST, `→ scatter_metablk`.
- `scatter_metablk` (task 14, `:90-92`) — forward the remaining `num_cols-1` (= 31) metas WEST in one
  fixed comptime op, `→ emit_scatter`.

**Phase B · KV segments WEST** (still pos0)
- `emit_scatter` (task 8, `:94-119`) — the `n_segs_rt == 0` fast-path above; otherwise stream
  `n_segs_rt` back-to-back `@mov32(scatter_dsd, seg_in_dsd)` of `seg_len` wavelets each, self-chaining
  on `emit_id`, and on the last one activating the role-bound post-row step.
  `seg_len` is **comptime** and `≤ 32766` — the runtime length lives entirely in the **count**
  (`:32-37`, `launch.py:1434-1452`), the repo's §11.7 rule (an extent `≥ 0x7fff` hangs silently).

**Phase C · per-round switch reset** (`round_sync`, `launch.py:1497-1508`)
- **tail** (`is_col_tail=1`, south-most, took the round's last row) `sync_src` (task 9, `:121-124`) —
  source one wavelet NORTH on `sync_out_q` (OQ4), then `@activate(peel_id)` to self-re-arm. The tail
  never left pos0, so it needs no reset.
- **non-tail** `sync_wait` (task 10, `:126-128`) — park on the RAMP copy of `round_sync` (IQ3).
- **non-tail** `sync_do` (task 11, `:130-133`) — `clear_current_position(in_color)` resets the switch
  to pos0, `@activate(peel_id)` re-arms for the next round.

`round_sync` runs **S→N**, opposite the southward data, so the sentinel can never overtake an
un-forwarded slice (`:19-23`). Route: tail `RAMP→N`; middles `S→[RAMP, N]` (tap *and* forward, the
router does the replication); north-most `S→RAMP` sink so it never leaks out of the band
(`launch.py:1500-1507`).

## Communication summary

| Movement | color / queue | direction | pattern | task(s) |
|---|---|---|---|---|
| row ingest from adaptor | `in_color` (region-alloc) / IQ2 | N→RAMP (pos0) · N→S (pos1) | **P-4 switch gather-scatter** | (fabric) → peel_meta0 |
| peel meta[0] (plen) | `in_color` / IQ2, 1 u32 | N→RAMP | **G-4 budget header** peel | peel_meta0 → scatter_meta |
| re-emit meta[0] | `scatter_color` 17\|21 / OQ3, 1 u32 | RAMP→W | **G-4** re-emit (count-neutral) | scatter_meta |
| forward `num_cols-1` metas | `scatter_color` / OQ3, 31 u32 | RAMP→W | fixed comptime block relay | scatter_metablk |
| KV segments WEST | `scatter_color` / OQ3, `n_segs_rt × seg_len` | RAMP→W | **P-4 seam** (runtime COUNT × comptime LENGTH) | emit_scatter |
| retain heartbeat | — (**zero wavelets**) | — | **fast-path: movement is zero** | emit_scatter `:98-106` |
| staircase gap bridge | `scatter_color` (relay) | E→W pass-through | **transparent relay** (`kv_fwd`, no program) | — (host-painted) |
| per-round re-arm | `round_sync` (region-alloc) / IQ3·OQ4 | S→N, 1 sentinel | **G-8-style column fence** | sync_src / sync_wait / sync_do |
| block west-shift (downstream) | `kv_ingress_color_{0,1}` 17/21 / IQ7·OQ7 | E→W, parity-swapped | **P-5 shift chain** | `decode.csl:1571, 1600` |

`scatter_color` is `kv_ingress_color_0` (id **17**) or `kv_ingress_color_1` (id **21**) chosen by the
**parity of the block's east-most fabric column** (`launch.py:1467-1469`), matching decode's west-shift
color swap. Ids 17/21 are reused from `kpipe_b k7` / `UP_A_color`, which live on strip and HT_head
cells — **PE-disjoint** from the block columns the west-shift runs on (`launch.py:623-626`).

## Related: `kv_fwd.csl` is the transparent extender (folded in here for the adaptor doc)

See the adaptor walkthrough for the `kv_fwd` subsection; on the injector side all that matters is that
for `by > 0` the WEST scatter crosses `by` columns of `kv_fwd` PEs painted `E→W` on both switch
positions (`launch.py:1475-1479`) before reaching the block's east edge. It runs no program.

## One line

One program on every injector PE; `is_col_tail` and the switch position are the only per-PE differences.
A host KV blob becomes a static SOUTH-walking switch column that peels a 4-word budget header, scatters
each row WEST as a runtime count of comptime-length segments, and — since S6a — recognises a `plen == 0`
retain heartbeat and advances the column **without moving a single wavelet**.
