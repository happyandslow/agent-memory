# kv_ingress_adaptor.csl — host-stream → injector-column relay (1 PE, per band)

> Kernel algorithm walkthrough. Model `qwen3_1p7b-decode`, ref config `test_sim_2x2block_kv_varlen.json`
> (`Pw=16`, `P_BLOCK_SIZE=8`, `P_Y_BLOCK_NUM=2` bands, `KV_DSD_SEG_MAX=100`).
> Diagram: `qwen3_1p7b-decode.kv_ingress_adaptor.svg`. Comms taxonomy per `cerebras-kernel-comm-patterns`.
> Covers `kv_ingress_adaptor.csl` **and** its transparent extender `kv_fwd.csl` (§ at the end),
> mirroring how the prefill series folded `kv_fwd` into `kv_egress_colmux`.
>
> **State documented: the CURRENT WORKING TREE of branch `lexu/staging/s6a-inner-pe-kv-route-a`
> (uncommitted S6a work on top of `fcfc8c1`).** Not at `fcfc8c1`: the meta tile widened
> `KV_META_LEN 2 → 4`, and the `n_segs_rt == 0` retain-heartbeat fast-path in `relay_kv`
> (`kv_ingress_adaptor.csl:82-92`).

## Core idea — a 1-PE store-free relay that cuts the host stream into row-slices

One adaptor PE sits between a band's TOP-edge H2D stream and the `1 × P_BLOCK_SIZE`
`kv_ingress_injector` column **directly south** of it (`kv_ingress_adaptor.csl:1-6`). Its whole job:
read the band's blob off the host port and re-emit it SOUTH **one row-slice at a time**, firing a
`SWITCH_ADV` control wavelet **between** rows so injector PE `k` catches row-slice `k` and forwards the
rest (`:3-5`). It is the 90°-rotated twin of the single-port `kv_adaptor` (EAST relay → SOUTH relay),
and follows the canonical SDK `sdklayout-05-gemv/demux_adaptor.csl` pattern (`:8-9`).

It **buffers nothing but one word**: `meta0_buf` is a `[1]u32` (`:36`) and everything else is
`fabin → fabout` at `@mov32`. KV is fp16 packed 2-per-u32 and the adaptor never reads the values, so
all counts are in **wavelets** (`:5-6`).

**Gate 0 / Gate 1.** Nothing is reduced or gathered — this is a pure serialization cut of a
host-ordered blob into a static per-PE permutation. The only runtime quantity anywhere on this path is
a **segment count**, derived identically on both ends from a header word; no wavelet is routed by key.

## Data distribution on PEs

| Element | Placement (2×2 config) | Role |
|---|---|---|
| host H2D stream `by` | TOP-edge port, capacity `kv_band_total` | one input stream per band (NS = `P_Y_BLOCK_NUM` = 2) |
| **adaptor** (this kernel) | 1×1 at `(STAIR_X0+by, y0-1)` | peel meta[0], relay rows SOUTH, `SWITCH_ADV` |
| `kv_ingress_injector` | 1 col × 8 at `(STAIR_X0+by, y0)` | takes row `ly`, scatters WEST |
| `kv_fwd` extender | `by` cols × 8 at `(STAIR_X0, y0)` | transparent E→W gap bridge (none for `by=0`) |
| decode block `by` | 16×8 at `(PLACE_X, y0)` | west-shifts the row across its columns |

Placement and wiring: `launch.py:1520-1547`. `STAIR_X0 = PLACE_X + Pw + 1`. The adaptor's BOTTOM output
port is `layout.connect`-ed to the injector column's TOP input port (`launch.py:1543`), and the host
stream is created on the adaptor's TOP port, optionally pinned via `KV_INGRESS_IO_LOCS`
(`launch.py:1536-1548`). The **staircase** (`+by`) exists so each band's TOP host port lands on a short,
non-degenerate routing rectangle to a top LVDS site — the §7.3 host-stream placer OOM avoidance noted in
`kv_fwd.csl:7-9`.

Host-side blob order is row-outer, matching the column: for `ly = 0..P_BLOCK_SIZE-1`, then `Pw` meta
tiles (W→E), then per `(layer, K|V)` the `Pw` column tiles W→E (`_repack_kv_band`,
`launch.py:2434-2482`).

## The metadata tile — the S6a widening, and what this PE reads vs forwards

Each row-slice on the wire is `[ num_cols metainfo u32 | KV ]` (`:12-15`). The metainfo block holds
**one tile per block column** so the block's west-shift can peel one per column.

**S6a widened the tile `KV_META_LEN 2 → 4` i16** (`launch.py:1413`, `decode.csl:1562`):

```
per-column meta tile = 4 × i16 = 2 × u32
  u32 #0 : [ i16 plen | i16 decode_len ]     ← the adaptor peels this word
  u32 #1 : [ i16 retained_len | i16 pad ]    ← rides through untouched
```
Host packing at `launch.py:2459`: `np.array([plen, dlen, rlen, 0], dtype=np.int16).view(np.uint16)`,
replicated `Pw` times per row.

`num_cols` is passed as `Pw * KV_META_LEN // 2` — the block **in u32** (`launch.py:1524`). So the
widening moved these extents:

| | at `fcfc8c1` (`KV_META_LEN=2`) | **now** (`KV_META_LEN=4`) |
|---|---|---|
| `num_cols` param | `Pw` = 16 u32 | **`2·Pw` = 32 u32** |
| `metablk_in/out_dsd` extent (`:41-42`) | `num_cols-1` = 15 | **31** |
| per-row wavelets | `Pw + C_kv·plen` | **`2·Pw + C_kv·plen`** (asserted `launch.py:2540-2543`) |
| meta words this PE *reads* | 1 (u32 #0, low 16) | 1 — **unchanged** |

**What this PE reads:** exactly one 16-bit field. `relay_meta` does
`n_segs_rt = D_kv * @as(u16, meta0_buf[0])` (`:69`) — the `@as(u16, u32)` truncation keeps `plen` and
throws away `decode_len` sitting in the high half. That truncation is precisely why widening the tile
required no change on this PE.

**What this PE forwards:** everything, byte-for-byte. The peeled word is **re-emitted** (`:71`) and the
other `num_cols-1` words relayed as one fixed comptime op (`:75`), so the injector and the block still
see the full `num_cols` metas. `decode_len` and `retained_len` are **never interpreted anywhere on the
transport path** — the adaptor and injector are blind to them; only the decode block PEs read them, in
`kv_ingress_meta_phase` (`decode.csl:1577-1579`), after west-shifting their own copy.

**`retain_rt` is derived, not sent.** There is no retain flag on the wire. Each block PE computes
`retain_rt = @as(i16, prefill_len_per_pe_rt == 0)` (`decode.csl:1580`) and, when set, skips the entire
per-layer K/V ingest (`decode.csl:1647-1653`) while `round_reset` keeps the existing cursor
(`decode.csl:290, 305`). Gate-1-lawful: the decision is **replicated bit-identically**, never routed on.

## The retain heartbeat and the `n_segs_rt == 0` fast-path (the subtle part)

A **retain round** sends `plen == 0`: the `num_cols` metas and **zero KV payload** — a meta-only
heartbeat whose entire purpose is to deliver this round's `decode_len` and `retained_len`.

`plen == 0` ⇒ `n_segs_rt = D_kv * 0 = 0`. **Before the fix**, `relay_kv` fell straight through to
`seg_idx += 1; if (seg_idx < n_segs_rt)` — `1 < 0` false — into the else branch, which **relays one
unconditional `seg_len`-wavelet `@mov32`** for a round that carried none. Consequences on the ingress
color:

1. a **phantom `seg_len` read** off the host port that was never sent, and
2. **undrained wavelets** left on the ingress color at the round boundary (the next round's data partly
   consumed as this round's segment).

Decode's per-round teardown **rebinds IQ7/OQ7 from the ingress colors back to broadcast**
(`decode.csl:1654` `kv_ingress_flush_then_resume`, column barrier `decode.csl:310-312`), and a queue can
only be rebound once drained. Residue on that color therefore surfaced as the observed **round-1 IQ7
remap FATAL** — a hard failure at the rebind, not a silent hang.

**The fix** (`:82-92`, twin at `kv_ingress_injector.csl:98-106`) short-circuits the segment relay and
goes straight to the inter-row bookkeeping:

```csl
if(n_segs_rt == 0) {
    seg_idx = 0;
    if(row_idx == num_rows - 1) { @activate(rearm_id); return; }   // last row -> re-arm the round
    @activate(advance_switch_id);                                   // else: SWITCH_ADV, next row
    row_idx += 1;
    return;
}
```

Note it reproduces **both** exits of the normal path: the `SWITCH_ADV`-then-next-row exit and the
last-row re-arm exit. That is the invariant — the column's switch still walks exactly `num_rows-1`
positions and the round still re-arms exactly once, whether or not KV moved. And because the injector
carries the matching fast-path, **both ends compute `n_segs_rt = 0` from the same peeled word**, so
count-exactness is preserved by construction.

## Communications + which task owns each step

Queues: `input_q` = **IQ2** bound to `host_in_color` (`adp.color("kv_adp_host")`, TOP-edge port,
`RAMP` output), `output_q` = **OQ2** bound to `inj_out_color` (`adp.color("kv_adp_out")`, painted
`RAMP→SOUTH`) — `:32-33, 127-128`, `launch.py:1526-1535`.

**Per row-slice:**
- `peel_meta0` (task 8, `:63-65`) — `@mov32` extent-1 peel of u32 #0 into `meta0_buf`, `→ relay_meta`.
- `relay_meta` (task 9, `:68-72`) — latch `n_segs_rt = D_kv * @as(u16, meta0_buf[0])`, `seg_idx = 0`,
  **re-emit** the peeled word SOUTH, `→ relay_metablk`.
- `relay_metablk` (task 11, `:74-76`) — relay the remaining `num_cols-1` (= 31) metas as one fixed
  comptime op, `→ relay_kv`.
- `relay_kv` (task 12, `:81-106`) — the `n_segs_rt == 0` fast-path above; otherwise self-chain
  `n_segs_rt` `@mov32(out_dsd, in_dsd)` ops of `seg_len` wavelets. On the row's **last** segment it
  branches on `row_idx`: last row → `rearm`, else → `advance_switch` (and `row_idx += 1`).
- `advance_switch` (task 13, `:108-110`) — emit **one control wavelet** on `output_q`
  (`ctrl_out_dsd`, `.control = true`, `:46`) carrying
  `ctrl.encode_single_payload(ctrl.opcode.SWITCH_ADV, true, {}, 0)` (`:48-49`), flipping the injector PE
  that just took its row from pos0 to pos1; then `→ peel_meta0` for the next row.
- `rearm` (task 10, `:112-117`) — `row_idx = seg_idx = n_segs_rt = 0`, `@activate(peel_id)`. There is
  **no barrier here**: `input_q` simply backpressures on the host port until the next round's blob
  arrives (`:116`). The injector column resets its own switches via its `round_sync` fence.

**Why `SWITCH_ADV` only *after* a row's last segment** (`:78-80, 99-102`): all `n_segs_rt` segments must
land on the same injector PE, so the switch must be held at pos0 for the whole row. And the **last** row
gets no advance at all — the south-most injector PE must stay at pos0 so it can source `round_sync`.

**Segmentation is a fabric limit, not chunked prefill** (`:19-22`). A row's KV can exceed the 16-bit
fabric DSD extent, and an extent `≥ 0x7fff` (`INFINITE_DSD_LEN`) **hangs silently** (§11.7). So
`seg_len` stays comptime and the length rides in the runtime **count**:
`C_kv = Pw · max_layers_per_block · bsz · kv_cols`, `seg_len` = the largest divisor of `C_kv` under
`KV_DSD_SEG_MAX`, `D_kv = C_kv / seg_len`, `n_segs_rt = D_kv · plen`
(`launch.py:1434-1452`). `launch.py:1453-1456` guards `D_kv · prefill_max_per_pe ≤ 65535`, since
`n_segs_rt` is a device `u16` that would otherwise wrap into a silent hang. `n_segs_rt == 1` is
byte-identical to a single `@mov32` (`:22`).

## Communication summary

| Movement | color / queue | direction | pattern | task(s) |
|---|---|---|---|---|
| host blob ingest | `host_in_color` (region-alloc) / IQ2 | TOP port → RAMP | H2D stream | (fabric) → peel_meta0 |
| peel meta[0] (plen) | `host_in_color` / IQ2, 1 u32 | →RAMP | **G-4 budget header** peel | peel_meta0 → relay_meta |
| re-emit meta[0] | `inj_out_color` / OQ2, 1 u32 | RAMP→S | **G-4** re-emit (count-neutral) | relay_meta |
| relay `num_cols-1` metas | `inj_out_color` / OQ2, 31 u32 | RAMP→S | fixed comptime block relay | relay_metablk |
| KV segments SOUTH | `inj_out_color` / OQ2, `n_segs_rt × seg_len` | RAMP→S | **P-4 seam** (runtime COUNT × comptime LENGTH) | relay_kv |
| retain heartbeat | — (**zero wavelets**) | — | **fast-path: movement is zero** | relay_kv `:82-92` |
| `SWITCH_ADV` | `inj_out_color` / OQ2, 1 **control** wavelet | RAMP→S | **P-4 switch step** (positional advance) | advance_switch |
| per-round re-arm | — (**IQ2 backpressure**) | — | no barrier; host port blocks | rearm |

Note the asymmetry worth remembering: the **adaptor** re-arms on nothing but backpressure, while the
**injector column** needs an explicit `round_sync` S→N fence, because its per-PE *switch position* is
round-carried state that must be cleared. The adaptor has no switch.

## `kv_fwd.csl` — the transparent extension (11 lines, no program)

`kv_fwd.csl` is a **pure-routing relay PE: no queues, no tasks, zero data memory** — its entire body is
an empty `comptime { }` (`kv_fwd.csl:1, 11`). It is the reversed mirror of the prefill egress extender
(`kv_fwd.csl:3-4`).

The host paints it in `launch.py:1475-1479`: a `by`-column × `P_BLOCK_SIZE` region at
`(STAIR_X0, y0)`, `paint_all(scatter_c, [rp_e2w, rp_e2w])` where
`rp_e2w = input EAST → output WEST` — the **same pass-through on both switch positions**, so the router
forwards every wavelet untouched regardless of switch state.

Its purpose is the **staircase gap**. The injector for band `by` sits at column `STAIR_X0 + by`, but the
block's east edge is at `PLACE_X + Pw - 1`; the extender fills the `by` columns between so the injector's
WEST scatter reaches the block. Equivalently (`kv_fwd.csl:5-9`): the staircase is what lets each band's
TOP host-input port sit on a short, non-degenerate routing rectangle to a top E/W LVDS site, avoiding the
§7.3 appliance host-stream placer OOM. Band `by = 0` needs no extender (`launch.py:1475`).

It occupies tiles and runs no program — the ingress column's transparent extender.

## One line

A single relay PE turns one host blob into `P_BLOCK_SIZE` row-slices walking a switch column south: peel
a 4-word budget header, re-emit it, relay the metas and a runtime count of comptime-length KV segments,
`SWITCH_ADV` between rows — and, since S6a, recognise a `plen == 0` retain heartbeat and step the switch
**without relaying a single KV wavelet**, which is what keeps IQ7 drainable at the round boundary.
