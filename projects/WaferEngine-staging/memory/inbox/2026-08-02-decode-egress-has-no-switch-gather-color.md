# S3b/E13 decode→host KV egress: the "clone prefill's switch-gather" plan has no valid color on the decode artifact

**Project:** WaferEngine-staging
**Author:** claude
**Status:** drained

## The situation this applies to

You are about to build the decode→host KV D2H egress (S3b / E13). The cheap-path design
on record ([[s3b-decode-kv-egress-options]]) is "clone prefill's `kv_egress_colmux`, have
block PEs **switch-gather EAST**, reuse colors 17/21 — 0 new colors." That topic explicitly
flags its color claim as INFERRED from manual grep and says *re-run `csl-color-audit`
before committing to any design that needs new fabric.* This is that re-run, and it
overturns the switch-gather recommendation.

## What the audit found (tool now fixed; occupancy is tool-verified)

`csl-color-audit` first had to be repaired — it crashed with a CoverageError on decode's
`@initialize_queue` because two binds in `ht_head.csl` span two lines and the extractor was
line-oriented (fix: fold continuation lines until parens balance; 254 tests pass, only two
multi-line forms exist in either repo).

On the decode artifact, **no color is simultaneously free + switch-capable + strip-clean
end-to-end** — the three properties an egress switch-gather needs:

- K-pipe occupies ids **7–17** (block interior is empty, but those colors are routed on the
  **east strip** the egress must cross).
- **17/21 are `kv_ingress`-owned** (already both switch-capable and in use).
- The only switch-capable, free, non-K-pipe, non-ingress color is **c0 (ht_ready)**, and it
  is **1-hop-only** under the WSE-3 long-route taboo — useless for a whole-column gather.
- **18/22** are strip-clean and owner-disjoint but **route-only (NOT switch-capable)**.

So prefill's switch-gather model cannot be cloned onto decode: there is no color to put the
`.switch` on.

## The design consequence

**Mirror the ingress west-shift as an EAST-shift parity chain instead** — a shift needs only
route-only colors, and 18/22 (a **parity pair**, not one color) suffice. Corollaries the
Codex review pinned:

- A parity shift needs **two** alternating colors (send/recv by fabric-column parity), same
  reason the ingress west-shift uses a 17/21 pair — see [[2026-08-02-switch-scatter-vs-parity-shift]].
- **OQ7 is the only flush-gated reusable queue** (needs a new handler state
  `broadcast → egress → ingress`).
- The new colmux column must sit **east of the entire ingress injector staircase**, not on
  `STAIR_X0`; the 18/22 W→E transit has to be threaded through the occupied staircase.

## Caveat

Design-level, Codex-reviewed, **not yet compiled or device-verified**. The color occupancy
is tool-verified; "the east-shift compiles and places" is not.

## Pointers

- [[s3b-decode-kv-egress-options]] (the switch-gather recommendation this refines), [[2026-08-02-switch-scatter-vs-parity-shift]]
- `launch_decode.py` color/queue allocation block; `models/qwen3_1p7b-e2e-pdSeparate/src/decode/`, `comm_pe.csl` (OQ7 rebind handler)
- `csl-color-audit` skill (now parses multi-line `@initialize_queue` binds)
