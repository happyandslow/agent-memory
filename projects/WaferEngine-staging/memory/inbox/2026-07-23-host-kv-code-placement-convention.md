# Where host-side KV-reuse / serving-control code goes: model root, one per kernel — not `waferengine/engine/`, not `models/<kernel>/host/`

Date: 2026-07-23 (session content from the M0/S6a planning round) · Repo: `WaferEngine-staging`

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured

## The situation this applies to

You are adding **host-side serving/control** code for one of the standalone kernels —
a KV-reuse store, a retain/warm-start driver, anything the `launch.py` serve loop calls
per round — and you have to pick a home for it. Three plausible-looking homes exist and
**two of them are wrong right now**, in ways nothing in the tree tells you:
`waferengine/engine/` looks like the architectural home; `models/<kernel>/host/` looks
like "the host code directory". A shared prefill+decode module also looks like the DRY
choice. The first S6a plan proposed `waferengine/engine/` and had to be revised.

## The convention (Le's explicit direction, twice, during S6a planning)

**Put it at the model root, beside `launch.py`, one copy per kernel:**
`models/qwen3_1p7b-decode/kv_store.py`, `models/qwen3_1p7b-prefill/kv_store.py`.
Keep it an importable module of its own (not inlined into `launch.py`) so the eventual
migration is a move, not a rewrite.

Why each alternative was rejected:

- **Not `waferengine/engine/`** — that package is **not yet wired to the kernels**,
  because the kernel form has not converged. The kernels will eventually ship as
  **compiled binaries**, so a host implementation has to be **versioned against a
  specific kernel version**. Until the form settles, host reuse logic stays next to the
  kernel it drives; extract to `waferengine/engine/` *later*, as the forms converge.
- **Not `models/<kernel>/host/`** — that directory is the **numerical-oracle / precision
  tooling** home (`oracle_fp16.py`, `oracle_prefill_fp16.py`, `approx_impact.py`,
  `gpu_side/`), which `launch.py` reaches through a `sys.path.insert(..., "host")` hack.
  Serving-control is a different concern from verification tooling; putting it there
  mixes the two. At the model root it is a plain sibling import of `launch.py` — no path
  hack.
- **Not one shared module for prefill and decode** — Le's reason: their **control
  policies may differ**. (They also hook two different `launch.py` serve loops.) A shared
  KV-compare module was likewise dropped: each kernel verifies against **its own existing
  oracle** instead.

Workflow that went with it: Le sketches the skeleton (class + function prototypes +
comments, fixing the path and signatures), the agent fills in the bodies.

## Status

This is what actually landed — `e0a19fc` (merged to `lexu/staging/kv-feature` via PR #1)
touches `kv_store.py` alongside `prefill.csl` / `ht_head.csl` / `launch.py` /
`comm_pe.csl`.

**Promotion candidate — procedural, not a one-off fact.** This is a placement rule for a
*class* of future additions (any host-side per-kernel control code while kernels are
still converging), plus the "extract to `waferengine/engine/` only after the kernel form
converges" trigger. It belongs in the repo-convention layer (CLAUDE.md / a review skill),
where it is loaded automatically, rather than in a topic someone has to know to look up.

## Pointers

- Plan the revision landed in: `docs/superpowers/plans/2026-07-13-m0-s6a-pe-internal-kv-reuse.md` (§ T0).
- Related: [[s6a-decode-kv-retain]], [[s6a-prefill-warm-start]] (the two consumers),
  [[standalone-vs-integrated-kernel-parity]] (why the kernel form has not converged yet).
