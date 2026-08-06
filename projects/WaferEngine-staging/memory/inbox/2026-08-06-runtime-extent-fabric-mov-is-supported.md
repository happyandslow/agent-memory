# A fabric @mov extent may be runtime, not only comptime — the real limit is extent < 0x7fff

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured

## The situation this applies to

You are designing a WSE-3 CSL fabric relay or egress (here: the E13 decode→host
KV D2H). Your payload has a varlen axis (decode: `plen` positions). You believe
a `@mov` into/out of a `fabout_dsd` **must have a comptime extent**, so you
contort the wire layout to keep the moved unit fixed-size and push the varlen
into a runtime *count* — e.g. choosing a "position-outer" emit (one comptime
`ML·KC` block per position, `plen` of them) over the simpler "raw-bank" emit
(one strided K/V run of length `plen` per feature). The raw-bank emit is what
mirrors the bank layout and lets the host stay opaque (memcpy, no transpose),
but you rejected it because its fabout extent is `plen` = runtime.

That belief is **wrong**, and it was driving the harder design.

## The finding

Runtime-extent fabric transfers are supported. Evidence from SDK source
(`csl_libraries/runtime/`, verified this session, Codex-confirmed):

- `mux_adaptor.csl:317-341` — `@set_dsd_length(gdsr_txact_dst, dsd_length)`
  (**runtime**) followed by `@mov32(..., .async=true)`: a runtime-length async
  fabric→fabric relay, in the SDK's own runtime library.
- `demux.csl:416`, `demux_N1.csl:222`, `spmv-hypersparse/pe.csl:1058` all set a
  runtime `@set_dsd_length` on a fabin/fabout DSD before the mov.
- The "fabin/fabout should be comptime for async" note in the spmv example is a
  caution for its *explicit-DSR-allocation* path; the mux/demux usage above is a
  direct counter-example. The real hard limit is **extent < 0x7fff** — above it
  the mov silently deadlocks (same wall as the ingress `metablk` comptime
  extent). For E13, `plen = ceil(L/256) ≤ 80`, so each K/V run is well under it.

**Why prefill uses comptime anyway:** prefill's KV is *chunk-structured*, so a
comptime chunk extent is natural and its varlen already lives in the chunk
*count* (`request_n_chunks`). That is a property of prefill's data, **not** a
fabric requirement. Decode has no chunk; position is its varlen axis, so a
runtime-extent raw-bank emit is the honest fit.

⇒ Decode egress can use **raw-bank** wire order: two strided `@mov` per PE
(whole K bank, then whole V bank), host does an opaque split+place (no transpose
— decode→host→decode is same-grid, unlike prefill→decode which needs
`kv_bridge`). This is the mirror of `kv_egress_colmux`'s payload-opaque model.

## The caveat that keeps it honest

Language-supported ≠ placement-safe. `prefill.csl:788` documents that a
**runtime-narrow** egress fabout once triggered PaintCompiler placement / OOM
failures on this exact path. So: use a comptime-MAX DSD template and narrow it
with `@set_dsd_length`, and treat "the runtime-extent emit compiles and places"
as a Step-1 compile-time gate, not an assumption. Verified at the source/design
level + Codex review; **not yet compiled or device-run.**

## Pointers

- Refines [[s3b-decode-kv-egress-options]] (which already had "emit raw order,
  host reorders") and [[decode-egress-has-no-switch-gather-color]].
- Related: [[switch-scatter-vs-parity-shift]], [[read-symbol-is-simulator-only]].
- Source: `csl_libraries/runtime/mux_adaptor.csl:317-341`, `demux.csl:416`;
  `models/qwen3_1p7b-e2e-pdSeparate/src/prefill/prefill.csl:788`,
  `kv_egress_colmux.csl`; host split-place in Gate-0 harness
  `host/e13_egress_gate0.py`.
