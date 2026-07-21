# Why widening prefill per-request metainfo touches ~4 files: it rides TWO separate streams, bridged at ht_head — 2026-07-21

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured

## The situation this applies to

You are about to add or widen a per-request metainfo field in
`models/qwen3_1p7b-prefill` (e.g. `start_chunk`, or a future S6b/M2 scalar).
You edit the obvious spot — the host prepend + the reader that consumes it — and
either it silently hangs, or you can't figure out why the same value seems to be
plumbed in two unrelated places with two different types. The failure mode is a
send/recv count mismatch on one of the streams: **silent deadlock, no compile
error** (the same class as the odd-extent hang and the `metainfo_len` cascade
already in [[s6a-prefill-warm-start]]).

## The finding — one metainfo value lives in two representations on two streams

The prefill kernel has **no shared control plane**; each region only sees the
stream flowing into it. A per-request scalar (`request_n_chunks`,
`last_token_chunk_pos`, `start_chunk`) therefore has to *ride the data*, and the
data changes representation partway through — so the same value is carried twice:

| channel | path | type | metainfo placement | key files/anchors |
|---|---|---|---|---|
| **front channel** (token-id) | host → demux → ht_head | **i32** (vocab may exceed i16) | **prepend** per token column | `launch.py` `build_request_stream` (host writes `metainfo_len` leading words per col), `demux.csl` (`OWN = ids_per_pe + metainfo_len`, opaque store-and-forward), `ht_head.csl` peel |
| **tail channel** (hidden-state) | ht_head → block0 → inter-block shuttle | **fp16** (X-tile is fp16) | **append** as X-tile tail | `ht_head.csl` re-stamps `meta` into fp16 tail (`OWN_LEN_META`), `prefill.csl` block reads tail at end of chunk, `comm_pe.csl` `shuttle_len = tile_size + metainfo_len` |

**ht_head is the bridge**: it peels the i32 metainfo off the token-id stream and
re-stamps it (as fp16) onto the X-tile stream, because token id → hidden state is
where the payload changes type. That is *why* the value exists in two forms.

Placement differs by consumer need: front channel **prepends** (ht_head must read
`request_n_chunks` before it knows how many chunks to drain); tail channel
**appends** (block compute addresses the X-tile by fixed position `[0, tile_size)`,
so metainfo can only ride as a tail the compute never touches). Both channels are
needed because their consumers are physically disjoint: ht_head only sees the
token-id stream; each compute block only sees the X-tile stream (the token-id
stream "becomes" the X-tile at ht_head and stops flowing).

## Why it matters (the transferable rule)

Widening prefill metainfo is not "edit `metainfo_len` + one reader." Both channels
carry the width as **separately hardcoded constants that must stay equal** — if
ht_head peels N off the front channel you must stamp N onto the tail channel and
every block/shuttle must read N. Miss one and the two streams desync → silent
hang. The mental model that makes the cascade predictable: **trace the value's
two rides (i32 prepend + fp16 append) and confirm the ht_head bridge re-stamps the
new width on both.** This is not a side channel — a new fabric color/queue for
metainfo is not free (block PEs have no spare queue), so metainfo piggybacks the
existing data streams, and FIFO order does the sequencing.

## Pointers

- Source read this session (branch `lexu/pdsep-...` / prefill working tree):
  `ht_head.csl`, `demux.csl`, `prefill.csl`, `comm_pe.csl`, `launch.py`
  `build_request_stream`.
- Complements [[s6a-prefill-warm-start]] (the widening *cascade* + odd-extent
  `csl-odd-extent-fabric-forward-hang` gotcha — the mechanical checklist; this note
  is the *why* behind it) and [[csl-control-payload-mechanisms]] (header-peel vs
  control-wavelet, and no-keyed-routing so metainfo must ride the data).
- Kernel-algo walkthroughs generated this session live in agent-memory
  `assets/kernel-algo/qwen3_1p7b-prefill.*` (now the
  `cerebras-kernel-algo-walkthrough` skill).
- **Promotion candidate** (reference, not just this field): "prefill per-request
  metainfo = two-channel (i32 token-id prepend + fp16 X-tile append) bridged at
  ht_head" belongs as an evergreen fact in the prefill kernel atlas / a review
  skill for anyone modifying prefill metainfo.
