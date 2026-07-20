# mux.csl — per-step logits egress (one PE, one blob per decode step)

> Kernel algorithm walkthrough. Model `qwen3_1p7b-decode`, ref config `test_sim_2x2block_kv_varlen.json`.
> Diagram: `qwen3_1p7b-decode.mux.svg`. Comms taxonomy per the `cerebras-kernel-comm-patterns` skill.
> **Git state: the CURRENT WORKING TREE of branch `lexu/staging/s6a-inner-pe-kv-route-a`, with the
> uncommitted S6a KV-retain work applied** — that is what enables the Design-X′ budget header and the
> per-round re-arm described below. Not a committed ref.

## Core idea — one PE, drained every step, re-armed every round

HT_tail runs the final RMSNorm, the lm_head GEMV, top-K and sampling. The global top-K is **replicated
across X** on the tail's root row, so the result already lives on a single PE — the tail's **root-row
east-most** cell (`launch.py:2279-2282`). Getting it off the wafer needs no gather: there is no keyed
routing (skill Gate 1), and none is required, because nothing is scattered.

So the mux is the skill's **Gate-1 lawful escape #2 — serialize through a mux PE** — in its cheapest
possible form: a **G-11 single-active-PE region**. Only the east-most mux cell binds any task; the rest
are inert (`mux.csl:101-113`). That cell drains the blob arriving from the **NORTH** and forwards it
**EAST** to the host output stream (`mux.csl:66-72`).

**Cadence — the difference from prefill's mux.** Prefill's `mux.csl` is the *one-shot* counterpart: one
blob, one TSC burst, done. Decode's mux runs a **three-level loop**, and the file itself names the
relationship (`mux.csl:5-7`):

```
per round  (NUM_ROUNDS = 3):
    init      : read 1-wavelet budget header N          (Design X′, KV_TRANSFER=1 only)
    per step  (up to N, early-stoppable):
        main  : drain  wavelets_per_step u32 from NORTH
        send  : forward them EAST to host
        next  : step++, loop or bail out
    tsc_recv / tsc_send : drain + forward one 8-u32 TSC burst
    -> re-activate init for the next round
```

That is **one blob per decode step**, not one per request. The TSC burst is **per round**, and the budget
header is **per round**. With `KV_TRANSFER=0` the header is skipped and `tsc_send` does not re-arm — the
kernel simply ends (`mux.csl:59-62,94-98`).

## Data distribution on PEs

mux region = **`HT_WIDTH_tail` columns (X) × 1 row (Y)**, placed at `(HT_HEAD_X, mux_y + P_BLOCK_SIZE)` —
one row south of HT_tail's bottom row, sharing HT_tail's X span so the east-most mux cell sits directly
under the tail's south emitter (`launch.py:2262-2264,2311-2313`; `mux_y` at `launch.py:710`).
Ref config: `HT_WIDTH_tail = 6` → **6 PEs, 1 active** (`launch.py:2283-2285`).

| Quantity | Value / sharding | Notes |
|---|---|---|
| `blob[N]` | `N = wavelets_per_step` u32 — ref config **N = 8** | staged then forwarded (`mux.csl:24-27`) |
| blob layout | `val_wavelets` packed-f16 top-K values ‖ `TOP_K·bsz` i32 indices ‖ `bsz` sampled token ids ‖ even-pad | ref: `2 ‖ 4 ‖ 2 ‖ 0` (`launch.py:2160-2169`) |
| `sampled_off` | `topk_wavelets_per_step` = **6** | offset of the sampled-token slot inside a blob (`launch.py:2276`) |
| `nstep_hdr_buf[1]` | i32 — this round's step budget `N` | Design X′ (`mux.csl:34-37`) |
| `tsc_blob[8]` | 8 u32 | per-round TSC burst (`mux.csl:50-53`) |
| `n_steps_runtime` | init `MAX_OUTPUT_LEN` = 16, overwritten by the header | `mux.csl:44-46` |

**Gate 0:** nothing is sharded across the mux row. The tensor is already on one PE, so the mux is a
**pure conduit** — no collective is involved or needed, and none should be added.

## Communications + which task owns each step

### Ingress from the north (P-6 point-to-point)

HT_tail's root-row east-most cell paints `RAMP→SOUTH` on `logits_south_color` at runtime, with
`NORTH→SOUTH` transit on the east-most cells below it down to `Edge.BOTTOM`
(`launch.py:2154-2159,2172-2178`). `layout.connect(ht_tail_logits_egress, mux_in_port)` wires that to the
mux's TOP ingress (`launch.py:2326`). The mux paints `in_color` **NORTH→RAMP on all six cells** — harmless
on the inert five, since only one has a queue bound (`launch.py:2288-2290`).

- **`init`** (`mux.csl:57-64`) — resets `step = 0`; if `kv_stream_ingress != 0` does a **blocking**
  1-wavelet `@mov32` to read the budget header into `n_steps_runtime`, then activates `main`. This is
  **G-4, a budget header prefixed to a variable-length stream** — decode's per-round step count is a
  runtime quantity, and the header is how the mux learns it without any handshake.
- **`main`** (`mux.csl:66-68`) — async `@mov32` drains `N` u32 off `in_q` into `blob`, activates `send`.

### Egress to the host (RAMP → EAST)

`host_color` (region color `host_out_color`) is painted `RAMP→EAST` **only on the east-most cell**, which
is the single-PE `Edge.RIGHT` output port (`launch.py:2265-2269,2291-2292,2304-2309`).

- **`send`** (`mux.csl:70-72`) — async `@mov32` forwards `blob` out east on `host_oq`, activates `next`.
- **`next`** (`mux.csl:74-85`) — `step += 1`, then the loop decision (below).

### Early stop (G-5 sentinel-in-payload)

`next` reads `blob[sampled_off]` as i32 and compares against `STOP_TOK = -2` (`mux.csl:22,79-84`). If the
blob just forwarded carries STOP_TOK — HT_tail has halted — or `step >= n_steps_runtime`, it jumps to
`tsc_recv` instead of looping. This matters: without it the mux would block forever on a `main` drain for
a blob HT_tail is never going to send. The stop signal rides **inside the payload**; no extra color, no
extra wavelet.

### TSC tail-relay + per-round re-arm (payload reuse, G-14-flavored)

After the step stream, the tail piggybacks one **8-u32 TSC burst** on the same south route — no separate
color, port or stream, deliberately reusing the proven tail→mux→host path (`launch.py:2111-2114`).

- **`tsc_recv`** (`mux.csl:87-89`) — drains the 8 u32 off the **same `in_q`**.
- **`tsc_send`** (`mux.csl:91-99`) — forwards them east on the **same `host_oq`**, and then branches: with
  `kv_stream_ingress != 0` it `.activate`s **`init`**, re-arming for the next round (the new `init`
  parks on the next round's header until HT_tail emits it); with `0` it completes and the kernel is done.

### Count-exactness (where a mistake becomes a silent hang)

Both ports are sized in `launch.py`, and the asymmetry is intentional:

| port | wavelets | why |
|---|---|---|
| `mux_in_port` (Edge.TOP) | `south_total_with_tsc + kv_hdr` | `+1` per round: the mux **consumes** the header (`launch.py:2298-2303`) |
| `mux_host_port` (Edge.RIGHT) | `south_total_with_tsc` | the header is **not** forwarded (`launch.py:2304-2309`) |

with `south_total_with_tsc = N × max_output_len_worst × num_rounds + 8 × num_rounds`
(`launch.py:2170-2171`) and `kv_hdr = num_rounds` when `KV_TRANSFER=1` (`launch.py:629-632`). The
`south_wavelets_per_step` even-padding (`launch.py:2168-2169`) exists because the D2H egress requires an
even per-step wavelet count — the kernel emits a matching dummy word and the host ignores it.

**Documentation caveat.** The banner comment above the mux region (`launch.py:2251-2260`) still describes
an older design — a W→E cut-through chain where each PE appends its own vocab band and the east-most PE
emits full `bsz*vocab` logits. **The shipped code does not do that.** Only one PE is active, and what
crosses the wire is the top-K/sampled blob, not full logits. Trust `mux.csl` and the per-PE
`is_last_pe` loop at `launch.py:2283-2285` over that comment.

## Communication summary

| Movement | color / queue | direction | pattern | task(s) | cadence |
|---|---|---|---|---|---|
| budget header `N` (1 i32) | `in_color` / `in_q` = IQ2 | NORTH → RAMP | **G-4 budget header** | `init` | **per round** |
| top-K/sampled blob (`N` u32) | `in_color` / IQ2 | NORTH → RAMP | **P-6 point-to-point** | `main` | **per step** |
| blob → host | `host_color` / `host_oq` = OQ2 | RAMP → EAST | Gate-1 escape #2, **G-11 single-active-PE** | `send` | **per step** |
| STOP_TOK detection | *(in-band, `blob[sampled_off]`)* | — | **G-5 sentinel-in-payload** | `next` | per step |
| TSC burst (8 u32) | `in_color` / IQ2, then OQ2 | NORTH → RAMP → EAST | **payload reuse on the same queue pair** | `tsc_recv` / `tsc_send` | **per round** |
| re-arm for next round | *(local `@activate`)* | — | multi-round re-arm | `tsc_send` → `init` | **per round** |

Everything rides **one** queue pair (IQ2 / OQ2) in strict FIFO order: `header, blob×N, burst×8`, repeated
per round. There is no reordering and no flow control beyond backpressure — correctness is entirely
count-exactness against HT_tail's emit counts.

## One line

Decode's mux is a single east-most PE that, **every decode step**, drains one top-K/sampled-token blob
from the north and pushes it east to the host — and **every round** brackets that loop with a 1-wavelet
budget header up front and an 8-u32 TSC burst at the end, then re-arms; the sampled-token slot inside the
blob doubles as the early-stop sentinel, so no extra color exists anywhere in this path.
