---
summary: How to offload decode-resident KV to host — the cheapest first-number path is cloning prefill's kv_egress_colmux onto decode (0 new colors/queues on a block PE); what is ruled out and why.
tags: [waferengine-staging, m2, s3b, kv-egress, design-options, cerebras]
---

# S3b · getting decode-resident KV off the chip — options survey

Research 2026-07-31 (read-only, no code written). Repo `/home/lexu/we-m2bench/models/qwen3_1p7b-e2e-pdSeparate`.
S3b is the last M2 item that **needs an implementation before it can be measured**; the offload half of
the offload-vs-recompute round trip has never been priced on a real path.

## Cheapest path to a first real number

**Clone prefill's egress onto decode, band 0 only.** Reuse `src/prefill/kv_egress_colmux.csl`
**verbatim** (116 lines, device-proven, includes the `round_sync` re-arm) as a new 1×256 column east of
`kv_inj_0`; block PEs switch-gather EAST; the existing 1×1 adaptor PE drains to a new host output
stream.

**Why it costs no new fabric on a block PE** (the constraint that killed the E9 block-PE design — see
[[e9-forced-segment-tsc]]):

- `kv_ingress_color_0 = 17` / `_1 = 21` are painted with **one** routing position each
  (`launch_decode.py:1276-1286`); a color has 4 switch positions ⇒ **2 free**. VERIFIED-IN-SOURCE.
- `OQ7` / `IQ7` are already **runtime-rebound** in production (`comm_pe.csl:1349-1355`,
  `decode.csl:1585-1586`). VERIFIED-IN-SOURCE.
- Exit port exists: decode's west OUT slots y = 19/37/55/73 are unused (`launch_decode.py:1668-1674`);
  the adaptor PE has **IQ/OQ 3..7 free** by its own comment (`kv_ingress_adaptor.csl:50-51`) with a
  proven contention-free east route (`launch_decode.py:1647-1665`).
- **No on-chip layout transform needed** — K strided (`decode.csl:1566`), V contiguous
  (`decode.csl:1575`); emit raw order, the host already reorders arbitrarily
  (`launch_decode.py:216-224`).

Cost ≈ **70 lines `decode.csl` + 120 lines `launch_decode.py`** plus the reused colmux. Run it as an
**exclusive round-boundary phase** (same shape as ingress) so it cannot perturb the decode data path.
Measure with a **payload sweep** (the `s30_bin*` bins already exist), never a single point.

Payload, code-derived and consistent with the established anchor: `max_layers_per_block = 4`,
`kv_cols = 4`, `kv_len_per_pe = 80` ⇒ **5,120 B/PE**; × 524,288 block PEs ⇒ **32 MiB per 256 tokens =
131,072 B/token**. `L = 8192` → **1.074 GB** total, 268 MB/band.

## Ruled out, with the evidence

| option | why it dies |
|---|---|
| `runtime.read_symbol()` | simulator-only — see [[read-symbol-is-simulator-only]] |
| logits south path carries bulk KV | `mux.csl:14,124-135` — **exactly one PE** forwards everything; a single-PE funnel for 1.07 GB. Throughput, not correctness |
| `kv_adp_tsc` stream as the carrier | it is on the **adaptor**, not a block PE; 8 u32/round, only when `KV_TSC=1`. **Its port is the right exit; the stream is not a carrier** |
| reverse the west-shift relay | possible but wrong: `decode.csl:1555-1556` is a **blocking CE store-and-forward**; the bottleneck column does ≈9,207 ops/round. The switch-gather does the same work with routers only |

## The block-PE resource constraint — now confirmed, not assumed

**All 16 queues are bound on a decode block PE**: OQ0 `decode.csl:891` + `comm_pe.csl:89`, OQ1/2
`comm_pe.csl:95-96`, OQ3-6 `:77-83`, OQ7 `:86`; IQ0 `decode.csl:910`, IQ1-7 `comm_pe.csl:85-94`.
⚠️ Colors 8-16 *appear* unpainted on block interior columns (`launch_decode.py:1298-1302`) — **INFERRED,
not verified against a route map**. Moot for the recommended option, which needs no new color.
⚠️ This audit was done by **manual grep, not `csl-color-audit`**. Re-run the skill before committing to
any design that does need new fabric.

## A correction this survey produced, and a falsifiable prediction

**Prefill's KV egress is NOT a layout transform.** `prefill.csl:101-104` says each PE switch-gathers its
**raw** K then V banks EAST, citing `csl-libs runtime/mux.csl + fft transpose.csl` as the **library
source of the switch-gather idiom** — not a transpose being applied; `prefill.csl:836-869` `@mov16`s raw
`K_cache_bank`/`V_cache_bank` chunks. The column↔layer permutation is **host-side**. ROADMAP said
otherwise and was corrected. ⇒ the layout mismatch that made decode-side egress look hard **does not
exist**.

**Prediction for the unexplained 46 ms ingress floor:** ≈ 9,207 store-and-forward steps × ~3.7 µs,
consistent with the ~4.54 µs/step figure already on record. INFERRED — **falsifiable by halving `Pw`,
which should halve the floor.** First testable explanation of that floor since M2-S1.

## Standing caveat on whether to build it at all

[[a7-Lp-vs-Lg-settled-on-tracelab]] removed S3b's *volume* justification: 99.7% of tokens are prompt
KV, and the host already retains that copy (A6, verified). What survives is an **architecture**
argument — decode-produced KV is the only KV with no host copy, so any cross-turn retention scheme
accumulates exactly the bytes S3b would move. **Le's decision, not a technical one.**

## Update — 2026-08-06: runtime-extent fabric `@mov` is supported

Drained from `memory/inbox/2026-08-06-runtime-extent-fabric-mov-is-supported.md`.

The earlier design pressure to keep fabric `@mov` extents comptime was too strong. SDK source shows
runtime-length fabric moves are supported when a DSD is narrowed with `@set_dsd_length` before the
move: `csl_libraries/runtime/mux_adaptor.csl:317-341` uses a runtime `dsd_length` followed by async
`@mov32`, and similar patterns appear in `demux.csl`, `demux_N1.csl`, and `spmv-hypersparse/pe.csl`.

The real hard wall is extent `< 0x7fff`; above it the move can silently deadlock, matching the known
ingress `metablk` extent wall. For E13, `plen = ceil(L/256) <= 80`, so a raw-bank decode egress where
the runtime extent is `plen` is below the wall. This means decode egress can use two strided moves per
PE — whole K bank, then whole V bank — and let the host split/place opaquely, with no on-chip transpose.

Caveat: language-supported does not imply placement-safe. `prefill.csl:788` records a prior
runtime-narrow egress fabout that triggered PaintCompiler placement/OOM failures. Use a comptime-MAX DSD
template, narrow it with `@set_dsd_length`, and treat “runtime-extent emit compiles and places” as a
Step-1 gate, not an assumption.

## Last updated

2026-08-10
