# mux.csl — one-shot logits egress (serialize through one PE)

> Kernel algorithm walkthrough. Model `qwen3_1p7b-prefill`, ref config `test_sim_2x4_kv_varlen.json`.
> Diagram: `qwen3_1p7b-prefill.mux.svg`. Comms taxonomy per the `cerebras-kernel-comm-patterns` skill.

## Core idea — one PE collects the tail's result and hands it to the host

After HT_tail runs lm_head + final-RMSNorm + top-K + sampling, the sampled token and top-K blob live on the
tail's **root-row east-most PE**. It has to leave the wafer through the host output stream at the east edge.
Rather than a keyed gather across the tail (there is no keyed routing — skill Gate 1), the mux uses **Gate-1
lawful escape #2: serialize through a mux PE** (`demux`→`mux` naming aside, this is the output collector).
Only the **east-most mux PE** participates; every other mux PE is inert (`mux.csl:53-63`). That one PE drains
the blob arriving from the **north** and forwards it **east** to the host, one straight pass-through
(`mux.csl:1-2,37-43`).

This is the **one-shot specialization** of decode's N-step logits mux: same `main → send → tsc_recv →
tsc_send` drain/forward/TSC-relay skeleton, minus the per-step loop, budget header, and early-stop
(`mux.csl:4-8`).

## Data distribution on PEs

mux region = **HT_WIDTH_tail columns (X) × 1 row (Y)** — one row **south** of HT_tail, placed at
`(ht_tail_x, ht_tail_y + P_BLOCK_SIZE)` (`launch.py:1396-1399,1418`). 2×4 config: **4 PEs**, only PE 3
(`is_last_pe=1`) active (`launch.py:1405-1407`).

| Quantity | Value / sharding | Notes |
|---|---|---|
| `blob[N]` | `N = wavelets_per_step` u32 (2×4: `N=32`) | the one-shot result, staged then forwarded (`mux.csl:15-17`). |
| blob contents | `TOP_K·bsz` packed-f16 values + `TOP_K·bsz` i32 indices + `bsz` sampled token (+even pad) | sizing mirrors ht_tail (`mux.csl:2-3`; `launch.py:1356-1362`). |
| `tsc_blob[8]` | 8 u32 | a TSC burst piggybacked after the blob (`mux.csl:26-30`). |

Nothing is sharded across the mux PEs — the tensor already lives on one tail PE, so the mux is a
**pure collector**, not a reduce.

## Communications + which task owns each step

**Blob ingress from the north (P-6 point-to-point)**
- The tail's root-row east-most PE emits the blob SOUTH down its east column to `Edge.BOTTOM` on
  `logits_south_color`; `layout.connect` wires that egress port to the mux's TOP ingress
  (`launch.py:1366-1369,1420-1421`). The mux's `in_color` is painted **NORTH→RAMP**, so the blob ramps into
  the east-most PE (`launch.py:1400,1408-1409,1412-1414`).
- `main` — `@mov32` drains the `N`-u32 blob off `in_q` into `blob`, then `@activate(send)` (`mux.csl:37-39`).

**Blob egress to the host (RAMP→EAST)**
- `host_color` on the east-most PE is painted **RAMP→EAST**, the host output stream's edge
  (`launch.py:1410-1411,1415-1417,1424-1425`).
- `send` — `@mov32` forwards `blob` out east on `host_oq`, then `@activate(tsc_recv)` (`mux.csl:41-43`).

**TSC tail-relay (payload reuse on the same queue pair)**
- After the blob, the TSC PE piggybacks **one 8-u32 burst** on the same south route; the mux drains and
  relays it so the host reads it as a second receive. It **reuses `in_q` / `host_oq`** — no new colors or
  queues (`mux.csl:26-30`; `launch.py:1363-1365`).
- `tsc_recv` — drain the 8-u32 burst into `tsc_blob`, `@activate(tsc_send)` (`mux.csl:45-47`).
- `tsc_send` — forward it east to the host edge, then **re-park `main`** for the next request
  (`mux.csl:49-51`).

## Communication summary

| Movement | color / queue | direction | pattern | task(s) |
|---|---|---|---|---|
| blob from tail (north) | `in_color` / `in_q`=iq2 | NORTH → RAMP | **P-6 point-to-point** (tail east col → mux) | main |
| blob to host | `host_color` / `host_oq`=oq2 | RAMP → EAST | **serialize-through-mux egress** (Gate-1 escape #2) | send |
| TSC burst relay | `in_color` / `host_oq` (reused) | NORTH → RAMP → EAST | **payload reuse on the same queue pair** | tsc_recv / tsc_send |

Both payloads ride the **same** `in_q`/`host_oq` in FIFO order (blob `N`, then burst `8`). Correctness is
**count-exactness**: the tail emits `south_total_with_tsc = N + 8` and the host receives exactly that
(`launch.py:1365,1412-1417`). A count mismatch on either leg is a **silent hang**.

## One line

The sampled-token result already sits on one tail PE, so the mux is not a collective — it is one east-most
PE that drains the blob from the north and streams it (plus a trailing TSC burst) east to the host, then
re-parks for the next request. The lawful wafer answer to "get a scattered result off-chip" is to serialize
it through a single collector PE, not to gather by key.
