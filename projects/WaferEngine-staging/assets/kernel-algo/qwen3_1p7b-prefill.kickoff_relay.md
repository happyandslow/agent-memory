# kickoff_relay.csl — forward-start TSC sentinel relay (fills the HT-band gap)

> Kernel algorithm walkthrough. Model `qwen3_1p7b-prefill`, ref config `test_sim_2x4_kv_varlen.json`.
> Diagram: `qwen3_1p7b-prefill.kickoff_relay.svg`. Comms taxonomy per the `cerebras-kernel-comm-patterns` skill.

## Core idea — keep a 1-wavelet sentinel from falling into empty tiles

The forward-start **kickoff** sentinel travels from **demux PE 0** down to the **HT_tail TSC PE** to anchor
the timestamp (TSC) forward-start on a single PE, so there is no cross-PE clock skew. It transits the HT
band (fabric column `x=HT_TAIL_X=4`) heading **NORTH→SOUTH** (`kickoff_relay.csl:1-9`).

For **> 2 block-rows** an unprogrammed gap opens in that HT band between `HT_head` (block-row 0, at the top)
and `HT_tail` (the last block-row, at the bottom). A wavelet routed into empty tiles hangs — **sim signal
11 / device TSC-PE park-hang** (`:6-8`). This kernel fills the gap with a **pure fabric relay**: every PE is
inert, the host paints `kickoff_color` `N→S` on the west column, and the router forwards the sentinel
straight through with **no PE program** (`:8-9`).

## Data distribution on PEs

No data. The relay region is `HT_WIDTH_tail × kickoff_gap_h`, placed at `x=HT_TAIL_X (4)`,
`y=PLACE_Y + P_BLOCK_SIZE`, directly under `HT_head` (`launch.py:1201-1209`). Height
`kickoff_gap_h = (by_last − 1)·P_BLOCK_SIZE` — for the 2×4 config `by_last=3`, so the gap is `2·8 = 16` rows
tall, only added when `> 2` block-rows leave a gap (`:1202`). Only the **west column** (`gx=0`) is painted
active; the rest is inert (paint `default_routing_pos`, `:1206`).

Each PE holds **no queues, no tasks, zero data memory** — the kernel body is an empty `comptime {}`
(`kickoff_relay.csl:10-12`). The one `param kickoff_color` exists only so the host can bind the color it
paints.

## Communications + which task owns each step

There is no task state machine — nothing runs on these PEs. The single movement is entirely a
**host-painted route**:

- `launch.py:1207-1208` — for each row `gy` of the gap, paint `kickoff_color` with `routing_pos_N_S`
  (`N→S`) on the west column (`IntVector(0, gy)`). The router forwards the 1-wavelet sentinel down the
  column with zero buffering.
- Source is demux PE 0 (`launch.py:1220, 1246`, `PE 0 → HT_tail TSC PE (SOUTH)`); sink is the HT_tail TSC
  PE, which consumes it as its forward-start anchor.

This is the "**never leave a transited color unpainted**" hard rule from the skill: paint an inert
pass-through rather than nothing, or the wavelet routes into empty tiles.

## Communication summary

| Movement | color / queue | direction | pattern | task(s) |
|---|---|---|---|---|
| kickoff sentinel | `kickoff_color` (id 17) / none | N→S, 1 wavelet | **transparent fabric relay** (1-wavelet barrier sentinel) | — (host-painted, no program) |

Correctness is trivial count-exactness: exactly one wavelet in, one wavelet out per PE, forwarded by the
router. The relay adds **zero PE program and zero data memory** — it exists only so the sentinel's path is
continuous.

## One line

A gap-filler, not a computation: paint `kickoff_color` `N→S` on one column so the forward-start TSC
sentinel crosses the empty HT-band gap between `HT_head` and `HT_tail` instead of hanging in unprogrammed
tiles.
