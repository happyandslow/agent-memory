---
summary: Runtime KV ingress for qwen3 decode so one compiled artifact can serve variable-prefill requests.
tags: [waferengine, qwen3, decode, kv-cache, serving]
---

# Dynamic KV load (qwen3 decode)

## Summary

Make the qwen3_1p7b-decode kernel load prefill KV **dynamically through chip
ingress at runtime** instead of baking it into the compiled program via
`set_symbol_all`. Baked KV ⇒ a new artifact + `runtime.load()` (~80s) per request
(batch model); dynamic KV ⇒ compile once, stream KV per request (streaming
serving primitive). This is the "dynamic-KV-loading decode kernel" the specdec
dual-kernel **M2 warm-start** depends on (`docs/2026-06-30/2026-06-30-specdec-dual-kernels-design.md`).

## Current state (2026-06-30)

DESIGN complete and approved; moving to implementation. Full design + per-file
plan + dataflow plot:
- `docs/2026-06-30/2026-06-30-qwen3-dynamic-kv-load-design.md` (+ `...-ht_head-dataflow.png`)

## Decisions

- **Option C (runtime symbol re-bind) is impossible** — SDK has no runtime
  symbol-write; `set_symbol_all` is `CodeRegion`/compile-time only. Binary-
  confirmed (`SdkRuntime::read_symbol` is read-only; only `CodeRegion::set_symbol_impl`
  writes). See [[reference_sdk_no_runtime_set_symbol]] (auto-memory).
- **memcpy (Option A) ruled out** by user (needs `memcpy_required=True`; pipeline
  is `memcpy_required=False`, all 24 colors spent). `bench/layer_block` already
  proves the cache `export var`s accept runtime `memcpy_h2d`, but we won't switch.
- **Option B chosen**: stream KV + kernel drain into the existing runtime-writable
  `XKCache_tile`/`XVCache_tile`; only the *initial fill transport* changes
  (`process_kv` already mutates them mid-decode).
- **Reuse the forward-path long-haul conveyor** (inter_block colors 19/20 + strip
  K-pipe relay), time-multiplexed in a pre-decode load phase. The strip relay's
  own-vs-forward split already = absorb-and-forward.
- **Intra-block distribution is the one new routine**: KV needs a 2D **scatter**
  (kv_dim on X, seq round-robin on Y), not the activation's **broadcast**. Reuse
  `intra_row_bcast` (id 6) route topology, peel-per-column.
- **Ingress: pass through HT** (reuse demux corridor) for simplicity — NOT a
  dedicated port. The demux corridor is HT-bound (`demux→pre_embed_x(18)→HT_head
  →post_embed_x(23)→row_0`); HT sits between west edge and decode blocks, so you
  can't reuse demux and skip HT.
- **HT_head relay = reuse C1(18)→diag→C2(23), skip the vertical UP/DOWN W_E
  gather.** C1/C2 are purely horizontal/per-row, so all rows relay KV in parallel;
  diag PE just drains C1 → emits C2 (skip embedding lookup). No new color/port;
  only a diag-PE load loop + port `data_size` bump + phase gate.

## Ordered tasks

1. Scatter spike (sim 2×2-block): intra-block X-peel, byte-exact vs `set_symbol_all`.
2. KV-extent transport: `decode_strip.csl` (N/S) + `comm_pe.csl` inter-block (E/W).
3. Ingress corridor: `demux.csl` + `ht_head.csl` load relays + host KV stream + port data_size.
4. `decode.csl` load phase + on-chip `iter_num` seeding + load→decode route repaint.
5. Regression gate: streamed-KV == baked-KV (ext_kv oracle).
