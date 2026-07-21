# Reasoning gotcha — a retain/reuse path's "preserved" state may be RECOMPUTED, not carried over — 2026-07-21

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured

## The situation this applies to

You are documenting or reviewing a KV-retain / prefix-reuse path and about to
write that on a reuse round it "continues" or "preserves" some derived state X
across the request boundary (position encoding, an accumulator, a running
phase). You reason: the *counters* are gated on retain (they are not rewound),
so the derived state must be gated too — carried straight over from the previous
round. **That inference is unsafe.** Check whether X is actually carried, or
whether it is recomputed from scratch every round *from* a carried-over counter.

## The concrete finding

`milestones/M0-reuse-foundation.md` (work repo) claimed a decode retain round
"continues the RoPE phase (skips the `(1,0)` re-seed)". Source says the opposite:
`round_reset` calls `rope_init_from_delta_p()` **unconditionally**
(`decode.csl:302`, guarded only by `kv_stream_ingress != 0`, **not** by
`retain_rt`), and that function **always** re-seeds `cos/sin` to `(1,0)`
(`:696-697`) and then rotates. The in-source comment states the intent: "from
(1,0) each round -> no cross-round drift." What retain actually changes is only
the **rotation count** — the loop runs `retained_len_per_pe_rt` times (`:699`),
and that variable is overwritten with the fresh prefill length only when
`retain_rt == 0` (`:290`). Phase continuity is *reconstructed by re-rotating*,
never *carried over*.

## Why it matters (the transferable lesson)

"Counters are gated on retain, therefore the phase is gated too" is an
**inference, not an observation**. RoPE state here is a *pure function of a
counter*, recomputed each round; it is not itself a retained counter. Whenever a
retain/reuse path is described, separate two categories explicitly:
**carried-over state** (survives the boundary in place) vs **state recomputed
from carried-over state** (re-derived every round, deterministically). They look
identical from the outside — same value crossing the boundary — but only one is
"preserved". This will recur when retain migrates to the integrated kernels
(S4/S5): the accessor being ported is the counter, and the phase is a downstream
recompute, so the port need not (and must not) try to "carry" the phase.

## Implications / next actions

- [x] Fixed `milestones/M0-reuse-foundation.md § S6a-decode`; logged in
  `PROGRESS.md` Failed approaches (work repo, 2026-07-21).
- [ ] Promotion candidate (procedural, would recur across the S4/S5 retain
  port): a maintain-pass call on whether "distinguish carried-over state from
  state recomputed from a carried counter" belongs in a CSL/retain review skill.
  Stated without the specific file it is a general review heuristic.

## Pointers

- `decode.csl:290, :302, :696-701` (WaferEngine-staging, branch
  `lexu/staging/s6a-inner-pe-kv-route-a`, uncommitted)
- Related topic: [[s6a-decode-kv-retain]] (line 34 already states the *correct*
  "RoPE seeded to eff_len"; this capture records the falsified doc + the lesson)
- Surfaced while generating the decode kernel-algo walkthroughs (agent-memory
  `assets/kernel-algo/qwen3_1p7b-decode.*`, commit `5c08bb2`)
