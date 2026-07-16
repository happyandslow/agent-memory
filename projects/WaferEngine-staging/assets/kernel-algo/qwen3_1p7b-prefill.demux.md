# demux.csl — host token-id ingress (1×P peel + fan-out)

> Kernel algorithm walkthrough. Model `qwen3_1p7b-prefill`, ref config `test_sim_2x4_kv_varlen.json`.
> Diagram: `qwen3_1p7b-prefill.demux.svg`. Comms taxonomy per the `cerebras-kernel-comm-patterns` skill.

## Core idea — peel your own column, pass the rest east, drop it south

The host has one flat token-id stream but the sequence is sharded **along X** across the HT_head columns
(`demux.csl:1-6`). The fabric cannot address a wavelet to "column *k*" (no destination field — skill
Gate 1), so the demux row is a **store-and-forward chain**: the whole stream enters PE 0 from the host;
each PE `local_px` **peels its own block** off the front of the stream, **forwards the remainder EAST**
to `local_px+1`, and **emits its own block SOUTH** into the HT_head column directly below it
(`demux.csl:75-80`). After the chain drains, every column holds exactly its own tokens — a static
permutation realized by a line of peel-and-forward hops, not by routing on a key.

The token ids are `u32` (i32 token ids — the vocab can exceed the i16 max), so all movement is `@mov32`
(`demux.csl:8`). Each column's block is `[metainfo_len leading words] ++ [ids_per_pe token ids]`; the demux
peels and forwards the whole block **opaquely** and HT_head decodes the metainfo prefix later
(`demux.csl:22-24`).

## Data distribution on PEs

demux region = **HWh columns (X) × 1 row (Y)** — one row **north** of HT_head (`launch.py:1211-1212,1247`;
`DEMUX_Y = PLACE_Y - 1` at `launch.py:381`). 2×4 config: **4 PEs** (`HWh = P/2 = 4`).

| Quantity | Value / sharding | Notes |
|---|---|---|
| `OWN` | `ids_per_pe + metainfo_len` (2×4: `8 + 3 = 11`) | one column's block: 3 metainfo words + its token ids (`demux.csl:24`). |
| `ids_per_pe` | `max_n_chunks·2·reduce_len` (2×4: `4·2·1 = 8`) | one head column feeds **2** HT_head block-columns, chunk-major (`launch.py:1127,1213`). |
| `metainfo_len` | `3` = `[request_n_chunks][last_token_chunk_pos][start_chunk]` | passed through opaquely; HT_head peels it (`launch.py:1214,1289-1296`). |
| `FWD_EXTENT` | `1` if last PE else `FWD_CHUNKS·OWN`, `FWD_CHUNKS = P_BLOCK_SIZE-1-my_idx` | wavelets this PE must relay east = all downstream columns' blocks (`demux.csl:25-26`). |
| `own_buf[OWN]` | local staging | the peeled block, re-emitted south (`demux.csl:28-29`). |

`P_BLOCK_SIZE` here is the **head width** `HWh`, not the layer block size (`launch.py:1215`) — it sets the
chain length and each PE's `FWD_EXTENT`.

## Communications + which task owns each step

**Host ingress + parity-alternating forward chain (P-5 store-and-forward + G-1 parity chain)**
- The full stream enters PE 0 on `in_color`; PE `local_px≥1` receives on a **chain color from the west**
  (`launch.py:1231-1232`). Adjacent hops alternate between two chain colors — **`chain_a` on even hops,
  `chain_b` on odd** — so two neighboring routers never paint the same color and conflict
  (`demux.csl:7`; `launch.py:1233-1240`).
- `main` — one `@mov32` peels `OWN` off `src_q` into `own_buf`; the shared `src_q` FIFO guarantees this PE's
  block sits at the front (**G-2 FIFO peel**), then branches on `is_last_pe` (`demux.csl:62-68`).
- `forward_and_out` (PE `local_px < P-1`) — a **second** `@mov32` on the *same* `src_q` streams the
  remaining `FWD_EXTENT` wavelets straight out east (`forward_oq`), and a concurrent `@mov32` emits `own_buf`
  south (`out_oq`). The two async microthreads join at `done` (`demux.csl:75-80`).
- `send_out` (PE `local_px == P-1`) — no east forward (`FWD_EXTENT=1` placeholder); just emit `own_buf`
  south (`demux.csl:70-73`).

**SOUTH emit into HT_head (feeds a P-2 multicast)**
- `out_color` = `tok_bcast_c` (color id 7); the demux paints it `RAMP→SOUTH` (`launch.py:1216,1223`). Each
  column drops its `OWN` block into the HT_head column below, where HT_head's `tok_bcast` color
  **multicasts it down the whole dim column** (‖Y) — the demux only does the R→S hop; the fan-out down Y is
  HT_head's router multicast (`launch.py:1162-1167`).

**Forward-start kickoff sentinel (1-wavelet barrier)**
- Only PE 0 (`is_kickoff_pe`): when its own block drains — i.e. its token column has landed, the true start
  of the forward — it emits a **1-wavelet sentinel SOUTH** on `kickoff_color` (id 17) via `kickoff_oq`
  (`demux.csl:36-42,58-60,71,77`). It transits the x=4 column down through HT_head into HT_tail's TSC PE,
  which samples its start-of-run TSC the moment it lands (`launch.py:424-429,1243-1246`).

**Per-request re-arm (queue re-park)**
- `done` re-arms the forward+out join gate (`@block(done_id)`) and `@activate(main_id)`, re-parking `main`
  on the host stream for the next request — the same compiled artifact serves arbitrary-length requests
  back to back (`demux.csl:82-86`).

## Communication summary

| Movement | color / queue | direction | pattern | task(s) |
|---|---|---|---|---|
| host token stream in | `in_color` / `src_q`=iq2 | host → PE0 (E) | **P-5 store-and-forward head** | main |
| forward remainder east | `chain_a`·`chain_b` / `forward_oq`=oq2 | X east (1-hop) | **G-1 parity chain** (A even hop / B odd) + **G-2 FIFO peel** | main / forward_and_out |
| emit own block south | `out_color`=`tok_bcast`(7) / `out_oq`=oq3 | SOUTH into HT_head | **R→S emit → P-2 multicast** (fan-out is HT_head's) | forward_and_out / send_out |
| kickoff sentinel | `kickoff_color`(17) / `kickoff_oq`=oq4 | SOUTH (PE0 only) | **1-wavelet barrier** | forward_and_out / send_out |

Correctness = **count-exactness**: each PE computes `OWN` and `FWD_EXTENT` from its own `my_idx`/
`P_BLOCK_SIZE`, and the host emits `HWh·(ids_per_head_col+3)` wavelets (`launch.py:1242`). Any mismatch
between what a PE peels+forwards and what its neighbor expects is a **silent hang**, not an error — which
is why widening `metainfo_len` must be applied on the host and every reader together.

## One line

Same program on every column; `my_idx` gives each PE a different peel offset and a different `FWD_EXTENT`.
A keyed host→column scatter becomes a line of peel-forward-drop hops with two parity colors — the standard
way to distribute a host stream along one axis on the wafer.
