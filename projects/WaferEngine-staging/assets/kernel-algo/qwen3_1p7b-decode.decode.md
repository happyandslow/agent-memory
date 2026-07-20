# decode.csl — one-token GEMV layer stack, round-resident, with conditional KV retain

> Kernel algorithm walkthrough. Model `qwen3_1p7b-decode`, ref config `test_sim_2x2block_kv_varlen.json`
> (2×2 blocks, 8×8 PE/block, 7 layers → `distribute_layers` = [1,2,2,2]). Diagram:
> `qwen3_1p7b-decode.decode.svg`. Comms taxonomy per the `cerebras-kernel-comm-patterns` skill.
> Citations `decode.csl:LINE` unless another file is named.
>
> **⚠ GIT STATE — this documents the CURRENT WORKING TREE, not a committed ref.** Branch
> `lexu/staging/s6a-inner-pe-kv-route-a`, **uncommitted** (`decode.csl`, `kv_ingress_adaptor.csl`,
> `kv_ingress_injector.csl`, `ht_tail.csl`, `launch.py` all dirty). The S6a KV-retain work described
> in §"The retain path" exists only here. Line numbers will not match `origin/main` or `fcfc8c1`
> (the file grew ~52 lines; e.g. `KV_META_LEN` moved from `:1535` to `:1562`).

## Core idea — the transpose of prefill: `m = 1`, so every GEMM is a GEMV + all-reduce

Every PE in a decode row-region runs this one file. Like prefill it owns a **contiguous slice of
transformer layers** (`layers_in_this_block`, `:66`; `set_layer(l)` repoints every weight/cache pointer
and loads that layer's `(iter_num, step)` bank, `:590`), and blocks are a **serpentine snake** passing
the hidden state `X` block→block (`inter_block_send_z`, `comm_pe.csl:1308`).

What differs is the shape of the work. Decode processes **one token**, so `m = 1` structurally: `C` is a
vector, not a matrix, and the P-1 vs P-3 crossover rule (`m > d`) says **all-reduce, never Cannon**.
There is no Cannon ring anywhere in this file — `run_matvec_f32` (`:409`) is a plain per-PE GEMV and
every projection is followed by a **P-1 two-phase chain all-reduce** along whichever axis the
contraction lives on. `decode_layer_body` (`:1424`) is a straight-line sequence of
GEMV → reduce → pointwise, punctuated by six `reconfig_allreduce_axis` calls (**G-3 runtime axis
repaint**) that flip one shared color set between the Y axis, the X axis, and the kv-head band.

The second difference is that decode is **round-resident**: one artifact serves `NUM_ROUNDS` requests
back to back. Each round re-ingests a KV prefix from the host, decodes `n_steps` tokens, barriers, and
re-arms its queues (**G-14**). The S6a work makes that round loop *stateful*: a round can now declare
itself a **retain round**, skip the KV ingress entirely, and continue decoding on the KV already in
SRAM.

## Data distribution on PEs

Each `row_y` region is `18 × 8` at `(9, 1)` / `(9, 9)` (`launch.py:1312`): `[lcl_x=0 west strip]
[lcl_x=1..16 block columns] [lcl_x=17 east strip]`. A block is `P_BLOCK_SIZE × P_BLOCK_SIZE` = 8×8.
`local_px` / `local_py` are block-local, recovered at runtime from fabric coords (`init_once`, `:270`).

**Decode's sharding is not one axis per tensor — it alternates, and that is what the six repaints are
for.** Gate 0 for anything you want to move here is: *which* of these rows is your tensor on.

| Tensor | Sharded on | Per-PE width | Reduce that contracts it |
|---|---|---|---|
| hidden state `X_tile` / `Z_tile` / RMSNorm gain | **Y** (`local_py`), **replicated along X** | `dim_per_pe` (ref 8) | `all_reduce_bsz_f32` on Y (`:934`) |
| Q output columns (`QKV_tile` Q region, `attn_out`) | **X** (`local_px`) | `attn_per_pe` (ref 8) | `all_reduce_bsz_dim` on X (`:1353`) |
| K/V head-dim columns | **X**, banded | `kv_cols` (ref 4) | band reduce on `px_in_kv_head` (`:1131`) |
| FFN inner dim | **X** | `ffn_dim_per_pe` (ref 16) | `all_reduce_bsz_dim` on X (`:1413`) |
| **KV cache sequence positions** | **Y, round-robin** | `kv_len_per_pe` slots (ref 4) | softmax + score·V on Y (`:1265`, `:1294`, `:1346`) |
| transformer layers | **block** (serpentine slice) | `layers_in_this_block` | — (never reduced across) |

The KV row is the load-bearing one. **PE `local_py = p` owns absolute positions `p, p+P, p+2P, …`** —
`process_kv` (`:1148`) writes only on the PE where `local_py == step mod P_BLOCK_SIZE` (`:1151-1152`)
and bumps its own `iter_num` (`:1180`). Everything that reads the cache sizes its DSD extent from
`iter_num`: `score_matvec_mult` (`:1200`, `:1206`, `:1213`, `:1237`), `softmax_score` (`:1257`),
`output_matvec_mult` (`:1318`). Cache layout is `K [b][kv_cols][kv_len_per_pe]` (position-minor) and
`V [b][kv_len_per_pe][kv_cols]` (position-major), layer-outer batch-inner (`:563`, `:566`).

**Consequence, and the whole reason retain is cheap: the live KV window is a per-PE *counter*, not a
placement.** Truncating, extending, or rewinding it moves **zero wavelets** — each PE just recomputes
its own `iter_num`. That is Gate 0's "the movement is nothing" case, and S6a exploits it directly.

X is replicated along the row because one PE per Y row receives it and multicasts east+west:
`is_x_receiver` sits at `lcl_x = 1 + root_2nd_phase` (`launch.py:1386-1389`), and the fan-out is
`bcast_dirs(local_px, root_2nd_phase, P_BLOCK_SIZE, WEST, EAST)` (`route_calc.csl:381`) — despite the
`_y_` in `intra_block_x_broadcast_y_bsz_dim`, **the routes are WEST/EAST**, i.e. along X. The `X` in
that name is the tensor, not the axis.

## The retain path — how "reuse the KV you already have" reaches the device

This is the S6a change and the single most important thing in the file. There is **no `retain` param**
on the decode region — retain is not compiled in, it arrives **as data**, one round at a time, through
the pattern the comm-patterns skill calls **G-13 (spare-slot scalar broadcast)**. The skill's own
warning applies and was heeded: *"do not widen `KV_META_LEN` casually — the extent is comptime and both
ends must change together, or you get the silent wavelet-count hang."* Both ends changed.

**1 · Host builds a 4-slot tile.** `_repack_kv_band` (`launch.py:2434`) emits
`meta_tile = [plen, decode_len, retained_len, pad]` as raw `i16` (`launch.py:2459`) — all three per-PE
counts (tokens ÷ `P_BLOCK_SIZE`). `start_idx` is chosen per round (`launch.py:2524-2531`): fresh round →
`pl_per_pe`; `RETAINED_LENS[r] == -1` → chain from `kv_store.last_idx`; else the explicit rewind point.
A **retain round sends `plen = 0`** — the per-round lower bound was relaxed `1 <=` → `0 <=`
(`launch.py:2489`) precisely to allow it.

**2 · `KV_META_LEN: 2 → 4`** (`:1562`), so the tile is 2 u32 wavelets instead of 1. The matching
comptime change on the transport side is `num_cols = Pw * KV_META_LEN // 2` on both the adaptor and the
injector (`launch.py:1487`, `launch.py:1524`).

**3 · Zero-length rows became legal.** With `plen = 0` the KV bulk phases have nothing to relay, so both
relays grew an explicit `n_segs_rt == 0` early-out that still advances the switch / still fires the
round-sync — `kv_ingress_adaptor.csl:82-91` and `kv_ingress_injector.csl:98-106`. Without these the
count-exact chain stalls: a zero-segment row would never reach its `SWITCH_ADV` or its sync.

**4 · Every block PE peels its own copy.** `kv_ingress_meta_phase` (`:1571`) runs the *same* count-exact
`@mov16` west-shift the bulk KV uses: column `c` receives `c+1` tiles and forwards all but its own
(`num_tiles = region_px + 1`, `:1643-1644`), on IQ7/OQ7 with the colors swapped by **fabric-column
parity** (`:1633-1637`, **G-1**). `@mov16` moves the i16 verbatim — no float conversion, so every PE
lands a **bit-identical** value, which is what makes the next line safe to branch on.

**5 · `retain_rt` is *derived on device*, from `plen == 0`** (`:1577-1580`):

```csl
prefill_len_per_pe_rt  = kv_meta_buf[0];
decode_len_per_pe_rt   = kv_meta_buf[1];
retained_len_per_pe_rt = kv_meta_buf[2];
retain_rt = @as(i16, prefill_len_per_pe_rt == 0);
```

Bit-identical replication is the **correctness mechanism** here, not an optimization (Gate 1): every PE
must take the same branch or the wavelet counts diverge and the device hangs silently.

**6 · The branch that saves the bandwidth** (`:1647-1653`): the entire per-layer K/V ingress loop is
wrapped in `if (retain_rt == 0)`. On a retain round **no KV crosses the fabric at all** — the meta tile
is the only traffic. The `kv_ingress_flush_then_resume()` rebind (`:1654`) runs either way, so the G-14
round state machine is unchanged.

**7 · `round_reset` conditionally retains instead of rewinding** (`:286`):

| | fresh round (`retain_rt == 0`) | retain round (`retain_rt == 1`) |
|---|---|---|
| `retained_len_per_pe_rt` | overwritten with this round's `prefill_len_per_pe_rt` (`:290`) | **kept** — the host's slot-2 value |
| `iter_num_bank[l]` (`:305`) | = fresh prefill length | = **retained length** (cache survives) |
| `n_steps` (`:298`) | `decode_len_per_pe_rt * P_BLOCK_SIZE` | same — decoupled from prefill either way |
| RoPE base (`:301`) | re-seeded to the prefill position | re-seeded to the **retained** position |

> **Correction to the S6a brief.** The brief states a retain round *"continues the RoPE phase (skips the
> (1,0) re-seed)"*. **The code does not skip it.** `rope_init_from_delta_p()` is called unconditionally
> whenever `kv_stream_ingress != 0` (`:297-302`), and it always re-seeds `(cos, sin) = (1, 0)` (`:696-697`).
> What S6a actually changed is the **rotation count**: the loop bound went `prefill_len_per_pe_rt` →
> `retained_len_per_pe_rt` (`:699`). The *outcome* is right — the angle lands at the retained position —
> but the mechanism is a re-seed with a different count, not a continuation. Worth knowing, because the
> cost is `O(retained_len_per_pe)` rotations per round rather than zero, and because the "no cross-round
> drift" property the comment claims (`:299-300`) depends on that re-seed still happening.

Note what is **absent** from all of this: no new color, no new queue, no new route, and on a retain round
no KV movement. The tier-0 in-place reuse M1 wants is, mechanically, a counter assignment at `:305` plus
a branch at `:1647`.

## Communications + which task owns each step

**Phase 0 · dispatch (`dispatch_init_task`, `:1657`)** — every PE binds the same tasks (`:1829-1838`);
this one picks the branch from fabric coords. Block PEs (`0 <= region_px < Pw_total`) → `@activate(init_task_id)`
(`:1669-1672`). Fake strips return immediately (`:1676-1679`). Real strips park IQ3..IQ7 on an unrouted
color, rebind IQ2/OQ7 to their K-pipe parity pair (`:1708-1714`) and hand off to `decode_strip.csl`
(`:1727`, `:1733`) — the **P-5 store-and-forward relay** that carries `Z` across the row-region boundary.

**Phase 1 · boot (`init_task_t`, `:1736`)** — `init_once()` (`:270`) runs `comm.init()` (paints all
collective routes), caches coords, computes `alpha`. Then, if `kv_stream_ingress != 0`, it calls
`kv_ingress()` **synchronously and returns** (`:1738-1744`) — block PEs sit idle through ingress; host X
just backpressures at HT_head. Otherwise `round_reset(); @activate(main_id)`.

**Phase 2 · KV ingress (`kv_ingress`, `:1630`)** — meta phase (§above), then, only if not retaining, per
layer: K phase then V phase (`kv_ingress_layer_phase`, `:1583`). Each phase is the same **P-5 west-shift
peel** (**G-2** FIFO peel: receive `c+1`, keep the last, forward the rest, `:1594-1600`) with **varlen by
`@set_dsd_length` clone** to this round's `prefill_len_per_pe_rt` (`:1589-1592`) — runtime *extent* on a
memory DSD, comptime on the fabric side. The received tile lands already in cache slab order (`:1601-1627`).
Ends in `kv_ingress_flush_then_resume()` → **G-14** drain OQ7 → rebind IQ7/OQ7 back to `broadcast_color`
→ `@activate(kv_ingress_resume_id)`.

**Phase 3 · `kv_ingress_resume` (`:1750`)** — `round_reset()` then `@activate(main_id)`. This is the
per-round entry; it runs every round, not just the first.

**Phase 4 · the step loop (`main`, `:1767`)**
- **Budget header (G-4)**: the result-sender emits `n_steps` as one `i32` wavelet on `result_color`
  *before* step-0 Z (`:1770-1773`), so HT_tail can bound its own loop.
- **X in** (`:1777-1781`): `is_x_receiver` PEs pull `bsz*dim_per_pe` from HT_head's stream on IQ0 /
  `x_input_color` (id 23) — a region-crossing **P-6**. All other block PEs call
  `inter_block_recv_x_sync` (`comm_pe.csl:1281`) on `inter_block_{a,b}_color` (19/20), the **P-6 snake hop**.
- **X multicast** (`:1785-1790`): `intra_block_x_broadcast_y_bsz_dim` (`comm_pe.csl:1295`) — **P-2 router
  multicast** on `intra_row_bcast_color` (6), source `local_px == root_2nd_phase`, interior PEs get a 2-tx
  route so the *router* replicates. When the strip is the source it instead runs a 1-tx forward chain
  (`comm_pe.csl:584-587`).
- **Early stop (G-5)**: `X_tile[0] < STOP_THRESHOLD_F16` (`:1797`) — HT_head floods the X path with
  `NEG_INF`. The check sits **before** any per-layer collective, and the PE forwards the sentinel
  downstream (`inter_block_send_z` + `result_out_dsd`, `:1798-1801`) before breaking, so no neighbor is
  left blocking on a missing wavelet.
- **`decode_struct` (`:1489`)** — restore `X_tile` from `X_input_tile`, `rope_step_advance()` once per
  step (`:1493`; RoPE is layer-invariant so all layers share the angle), then loop `layers_in_this_block`:
  `set_layer(l)` → `decode_layer_body()` → write `(iter_num, step)` back to the banks (`:1498-1499`) →
  chain `X = Z` (`:1501`).
- **Z out** (`:1811`): `inter_block_send_z` to the serpentine-next block (**P-6**), on the opposite color
  from recv (`comm_pe.csl:1312-1316`). The snake-tail edge column additionally streams Z to HT_tail on
  `result_color` / OQ0 (`:1815-1817`, **P-6** region crossing).
- **Round end** (`:1823-1826`): `round_barrier()` (`:314`) — a Y all-reduce whose value is discarded,
  used purely as a **column fence** so no PE rebinds IQ7 while a neighbor still broadcasts on it — then
  `kv_rebind_to_ingress_flush()` (**G-14** in the other direction) → `round_reingress` (`:1757`) →
  `kv_ingress()` for the next round.

**Phase 5 · one layer (`decode_layer_body`, `:1424`)** — the axis of every reduce, in order:

| step | fn | contraction | axis | reduce |
|---|---|---|---|---|
| RMSNorm(X) | `rmsnorm_x` `:970` | hidden dim | **Y** | `all_reduce_bsz_f32` `:934` (**P-1**) |
| Q, K, V proj | `:972`, `:978`, `:984` | hidden dim | **Y** | `all_reduce_bsz_dim_QKV_fusion` `:1431` (**P-1**, three reduces fused into one) |
| *repaint* | `reconfig_allreduce_axis(3)` `:1434` | | Y → kv-band | **G-3** |
| QK-Norm | `qk_norm_q_k` `:1128` | head_dim | **X band** | `all_reduce_qk_kv_head_scoped` `:1131` (**P-7**, Q and K sumsq fused into one reduce) |
| RoPE Q, K | `:1051`, `:1052` | — | local | none |
| append KV | `process_kv` `:1148` | — | local | none (owner PE only) |
| Q·Kᵀ | `score_matvec_mult` `:1188` | head_dim | **X band** | `..._kv_len_kv_head_scoped` `:1231` (**P-7**) |
| *repaint* | `reconfig_allreduce_axis(0)` `:1448` | | band → Y | **G-3** |
| softmax | `softmax_score` `:1245` | KV positions | **Y** | max `:1265` **then** sum `:1294` (**P-8**, two-pass safe softmax) |
| score·V | `output_matvec_mult` `:1312` | KV positions | **Y** | `all_reduce_bsz_dim` `:1346` (**P-1**) |
| *repaint* | `reconfig_allreduce_axis(1)` `:1454` | | Y → X | **G-3** |
| O proj | `o_matvec_mult` `:1350` | attn cols | **X** | `all_reduce_bsz_dim` `:1353` (**P-1**) |
| residual | `attn_residual_add` `:1357` | — | local | none |
| *repaint* | `reconfig_allreduce_axis(0)` `:1460` | | X → Y | **G-3** |
| RMSNorm(Z) | `rmsnorm_z` `:1364` | hidden dim | **Y** | `:934` (**P-1**) |
| up, gate | `:1366`, `:1371` | hidden dim | **Y** | `all_reduce_bsz_ffn_dim_ZZ_fusion` `:1466` (**P-1**, fused) |
| SwiGLU | `ffn_gate_silu` `:1376`, `ffn_swiglu_mul` `:1403` | — | local | none (deg-6 poly SiLU, D-cache pinned) |
| *repaint* | `reconfig_allreduce_axis(1)` `:1473` | | Y → X | **G-3** |
| down proj | `down_matvec_mult` `:1410` | FFN dim | **X** | `all_reduce_bsz_dim` `:1413` (**P-1**) |
| residual | `ffn_residual_add` `:1417` | — | local | none |
| *repaint* | `reconfig_allreduce_axis(0)` `:1479` | | X → Y | **G-3**, restores the entry axis |

The repaints are unfenced and safe **only** because every `all_reduce_*` on those colors is synchronous
and ends in a multi-tx broadcast, making the collective self-fencing — the invariant is spelled out at
`comm_pe.csl:1325-1334`, and breaking any of its three clauses turns it into a device-only (sim-green)
C1 hang.

## Communication summary

| Movement | color / queue | direction | pattern | task / fn |
|---|---|---|---|---|
| **KV meta tile `[plen, dlen, rlen, pad]`** | kv_ingress 17/21 / IQ7,OQ7 | X west (peel) | **G-13** scalar broadcast (widened 2→4) + **G-1** parity + **G-2** peel | `kv_ingress_meta_phase` `:1571` |
| KV bulk prefix (skipped on retain) | kv_ingress 17/21 / IQ7,OQ7 | X west (peel) | **P-5** shift chain + **G-2** + **G-12** payload-opaque `@mov16` | `kv_ingress_layer_phase` `:1583` |
| ingress ⇄ broadcast queue rebind | — (queue state) | — | **G-14** flush-gated rebind | `kv_ingress_flush_then_resume` / `kv_rebind_to_ingress_flush` |
| X in, chain start (from HT_head) | x_input 23 / IQ0 | region cross | **P-6** | `main` `:1778` |
| X in, other blocks | inter_block 19,20 / q0,q1 | snake hop | **P-6** | `inter_block_recv_x_sync` |
| X multicast in block | intra_row_bcast 6 / IQ2,OQ0 | X (W+E) | **P-2** router multicast | `intra_block_x_broadcast_y_bsz_dim` |
| RMSNorm / QKV / FFN-norm / up-gate reduce | reduce 1,2 + 3,4 + bcast 5 | **Y** chain | **P-1** two-phase all-reduce | `all_reduce_bsz_f32` / `*_QKV_fusion` / `*_ZZ_fusion` |
| QK-Norm + Q·Kᵀ reduce | same ids, X-band routes | **X** band | **P-7** band reduce | `all_reduce_*_kv_head_scoped` |
| softmax max, then sum | same ids, Y routes | **Y** | **P-8** two-pass safe softmax | `all_reduceMax_bsz_gqa_group` → `all_reduce_bsz_gqa_group` |
| O proj / down proj reduce | same ids, X routes | **X** chain | **P-1** | `all_reduce_bsz_dim` |
| axis flip between the above | same ids, 5 `@set_config` writes | — | **G-3** repaint | `reconfig_allreduce_axis` `:1335` |
| Z out → next block | inter_block 19,20 / q0,q1 | snake hop | **P-6** | `inter_block_send_z` |
| Z across row-region boundary | kpipe a/b pairs / IQ2,OQ7 | Y relay | **P-5** store-and-forward | `decode_strip.csl` |
| per-step Z → HT_tail | result_color / OQ0 | region cross | **P-6** | `main` `:1816` |
| round budget `n_steps` → HT_tail | result_color / OQ0 | region cross | **G-4** budget header | `main` `:1770-1773` |
| early-stop sentinel | rides the X multicast + Z sends | with X | **G-5** sentinel-in-payload | `main` `:1797-1803` |
| round fence before rebind | reduce/bcast colors | Y | column fence (discarded all-reduce) | `round_barrier` `:314` |
| **retain: KV rewind / extend** | **none** | **none** | **Gate 0 — no movement; a counter edit** | `round_reset` `:305` |

Correctness is **count-exactness**: both ends of every link derive the same wavelet count from PE
coordinates or from a bit-identically replicated runtime scalar. There are no acks and no credits — a
count mismatch is a silent hang. The S6a widening is exactly the risky kind of edit (a comptime extent
on both ends), which is why the host `num_cols` and the two relays' zero-segment early-outs had to move
with it.

## One line

One program per PE runs a contiguous slice of transformer layers for a **single** token, so every
projection is a GEMV closed by a **P-1 chain all-reduce** rather than a Cannon ring, with **G-3**
repaints flipping one color set between the hidden-dim Y axis, the attention/FFN X axis, and the kv-head
band; blocks pass `X` along a serpentine snake (**P-6**/**P-5**) and stream Z to HT_tail; and because
the KV cache is sharded round-robin on Y with the live window set purely by each PE's own `iter_num`
counter, the S6a retain round reuses it by shipping one widened **G-13** metadata tile
(`[plen, decode_len, retained_len, pad]`, `retain_rt` derived on-device from `plen == 0`) and then
moving **zero** KV bytes.
