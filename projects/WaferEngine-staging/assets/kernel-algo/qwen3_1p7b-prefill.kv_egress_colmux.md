# kv_egress_colmux.csl — KV-cache egress column-mux (NORTH drain to host)

> Kernel algorithm walkthrough. Model `qwen3_1p7b-prefill`, ref config `test_sim_2x4_kv_varlen.json`.
> Diagram: `qwen3_1p7b-prefill.kv_egress_colmux.svg`. Comms taxonomy per the `cerebras-kernel-comm-patterns` skill.
> Covers `kv_egress_colmux.csl` **and** its transparent extender `kv_fwd.csl` (same topology, one diagram).

## Core idea — drain each row NORTH, one at a time, with a switch that walks down the column

After prefill, each compute block-row holds a slice of the KV cache. To get it off-wafer, each region's
rows first **gather EAST** on a shared row color (`kv_egress_c`, id 21) to the region's east edge; there a
**1×P_BLOCK_SIZE column of mux PEs** (this kernel) drains those rows **NORTH** to a single top-edge host
stream. This is the egress half of the switch-level gather/scatter KV bridge — decode's mirror is the
host→device WEST scatter `qwen3_1p7b-decode/src/kv_ingress_injector.csl` (`kv_egress_colmux.csl:4-5`).

The mux is a **router-switch column drain** (skill pattern **P-4** seam / switch gather-scatter). Each mux
PE is a `fabin → fabout @mov32` — its row's bytes **never land in PE memory** (`:8-10`). The north-most PE
drains first (route `RAMP→N`); after its own row it fires a `SWITCH_ADV` to flip to `S→N`, so every row to
its **south** then threads straight through it to the host. Rows drain north one-by-one; correctness is
pure **count-exactness** — a switch flipped one wavelet early or late silently hangs.

**VARLEN** (`:14-16`): the row's chain-head prepends `request_n_chunks` (1 u32) ahead of the payload. The
mux **peels** it (not forwarded), latches `n_segs_rt = rnc`, then drains `n_segs_rt` segments of `seg_len`
u32 each. `seg_len` is a **comptime** fabric-extent unit (`< 32767`); the request's true length is carried
by the **runtime segment count**, never the segment length — the repo's §7.3-safe "runtime COUNT × comptime
LENGTH" rule (`launch.py:757-760`, i16 extent guard at `:766-768`).

## Data distribution on PEs

Per region (block-row `by` of `P_Y_BLOCK_NUM`), the mux is **1 column × P_BLOCK_SIZE rows** on the wafer's
**EAST** side, staircase-offset by `by` columns (`launch.py:1050-1057, 1087, 1111`).

| Element | Placement (2×4 config) | Role |
|---|---|---|
| compute region `by` | `Pw`×`P_BLOCK_SIZE` = 16×8, at `x=PLACE_X(8)`, `y=2+by·8` | holds KV, gathers rows EAST on `kv_egress_c` |
| `kv_fwd` extender | `by` cols × 8, at `x=STAIR_X0(24)`, `y=2+by·8` (none for `by=0`) | transparent W→E relay bridging the staircase gap |
| **colmux** (this kernel) | 1 col × 8, at `x=24+by`, `y=2+by·8` | peel + segmented NORTH drain switch |
| host output stream | TOP edge port above column `24+by` | one D2H stream per region (NS = `P_Y_BLOCK_NUM` = 4) |

Each mux PE holds essentially **no data**: a 1-word `meta_buf` for the peeled `rnc` and a 1-word `sync_buf`
for the sentinel (`:46-47, 53-54`). The **staircase** (drain column `= STAIR_X0 + by`) gives every region a
clear vertical path north to an open top edge; the west-side gap to the drain column is filled by the
`kv_fwd` extender so the east-gathered row can reach it (`launch.py:1080-1085`).

**`kv_fwd.csl` — the transparent extension.** A pure-routing relay PE: **no queues, no tasks, zero data
memory** — its body is an empty `comptime {}` (`kv_fwd.csl:1, 15`). The host paints `kv_egress_c` as a
pass-through switch position (`fwd_w2e = [W→E, W→E]`, `launch.py:1076, 1084`) so the router forwards every
wavelet untouched across the `by`-column gap. It occupies tiles but runs no program; it is the egress
column's transparent extender, adopted from the §11.6 multi-stream egress bench (`kv_fwd.csl:3-9`).

## Communications + which task owns each step

**Row ingest (P-2 gather tail → this column's WEST):** each mux PE receives its row on `in_color` (id 21)
via `in_q` (input queue 2), routed `WEST→RAMP` (`launch.py:1092`). The row arrives `rnc`-prepended.

**Phase A · peel + segmented NORTH drain**
- `peel_meta` (task 8) — `@mov32` peels the leading `request_n_chunks` into `meta_buf` (1 u32, **not**
  forwarded to host); `@activate(drain)` (`:65-67`).
- `drain` (task 9) — on the first entry latch `n_segs_rt = meta_buf[0]`; then, while `seg_idx ≤ n_segs_rt`,
  `@mov32(seg_out_dsd, seg_in_dsd)` streams one `seg_len` segment `fabin→fabout` NORTH and re-activates
  itself. The north-most PE at `pos0` routes its own row `RAMP→N`; PEs below route `S→N` once flipped
  (`:68-77`). When segments are exhausted, `@activate(after_drain_id)` (the role-bound post-drain step).

**Phase B · role-bound post-drain + per-request re-arm barrier** (`out_color` route + `round_sync` id 10)
- **non-tail** `sync_wait` (task 10) — emit one `SWITCH_ADV` control wavelet on `out_color` (flip this PE
  from `RAMP→N` to `S→N` so the rows below forward through it), then **park** on `round_sync` via
  `@mov32(sync_buf_dsd, sync_recv_dsd, …activate=sync_do)` (`:92-95`).
- **tail** (`is_col_tail=1`, south-most, structurally last to drain) `sync_src` (task 10) — **source** one
  `round_sync` wavelet NORTH (fire-and-forget), a no-op `clear_current_position` (tail never left `pos0`),
  then `@activate(peel_id)` to self-re-arm. **No `SWITCH_ADV`**: the tail has no south row, and a tail
  advance would race the reset (`:79-89`).
- **non-tail** `sync_do` (task 11) — fires only after the tail's sentinel has threaded up through every
  south PE (i.e. all rows below have drained); `clear_current_position(out_color)` resets the switch to
  `pos0` and `@activate(peel_id)` re-arms for the next request (`:96-100`).

**round_sync topology** (`launch.py:1094-1106`): a **separate non-switch** color (id 10) painted `S→N` per
region — tail (south-most) sources `RAMP→N`; middles tap+forward `S→[RAMP,N]`; north-most (host-facing)
sinks `S→RAMP` so the sentinel never leaks past the region. It is the vertical rotation of the
device-proven SOUTH-gather `round_sync` re-arm barrier (`:20-28` of the kernel).

## Communication summary

| Movement | color / queue | direction | pattern | task(s) |
|---|---|---|---|---|
| row ingest into mux | `in_color` 21 / in_q2 | W→RAMP | **P-4 seam** (gather tail) | (fabric) → peel_meta |
| peel `rnc` header | `in_color` 21 / in_q2 | W→RAMP, 1 word | **G-4 budget header** peel | peel_meta |
| NORTH row drain | `out_color` {6,8,9,17} / out_q3 | RAMP→N then S→N | **P-4 switch gather-scatter** (`SWITCH_ADV` walk) | drain / sync_wait |
| staircase gap bridge | `kv_egress_c` 21 (relay) | W→E pass-through | **transparent relay** (`kv_fwd`, no program) | — (host-painted) |
| per-request re-arm | `round_sync` 10 / in_q3·out_q4 | S→N, 1 sentinel | **G-8-style column fence** (round barrier) | sync_src / sync_wait / sync_do |

Correctness is **count-exactness**: both ends compute the same wavelet count from `seg_len` (comptime) ×
`n_segs_rt` (= peeled `rnc`, bit-identical on the head). A `SWITCH_ADV` on the wrong PE, or a segment-count
mismatch, is a **silent hang**, not an error. The tail-vs-middle role split exists precisely so the switch
is reset only *after* the whole column has drained (`:20-28, 79-83`).

## Related: route_util.csl / route_calc.csl are comptime routing helpers, no runtime algorithm

`src/route_util.csl` and `src/route_calc.csl` are **compile-time routing helpers** imported by the compute
kernels (`comm_pe.csl`, `ht_head.csl`, `ht_tail.csl`) — a color-config route/word calculator
(`route_util.csl:28-74`) and a per-PE reduce-direction calculator (`route_calc.csl:81-185`). They export
`inline fn` / `fn` only, hold **no per-PE task state machine, no queues, no `@bind_local_task`**, and never
run as a PE program. They get this note, not a diagram.

## One line

Same program on every mux PE; `is_col_tail` and the switch position are the only per-PE differences. A KV
cache scatter-to-host becomes a static NORTH-draining switch column plus a peeled length header — the
wafer-native way to serialize many rows onto one D2H stream, re-armed each request by a 1-wavelet column
barrier.
