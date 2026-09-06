# A stateless-position refactor drops the guard the old counter carried — 2026-08-30

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured

## Situation this applies to

You are replacing a stateful, incrementally-updated counter in a decode kernel
(a shared `iter_num`/`step` advanced once per step, whose increment sits behind
a write guard) with stateless arithmetic derived from `position` — e.g. the
M1b-S0 Part 1 move to per-request `current_len` inside fixed request segments.
The refactor compiles, the local compile-only gate is green, short-sequence
runs look fine, and every reviewer's checklist (DSD binds, slot order, empty
identities, collective ABI, bsz=1 equivalence) passes. Nothing announces the
problem: the failure only exists once a sequence is long enough to fill the
per-PE KV capacity, and then it is a silent out-of-bounds read, not a crash.

## Finding

The old `iter_num` carried **two** semantics, not one: a count, and a
**saturation** — its increment was guarded so it stopped at `kv_len_per_pe`
(the current token is silently dropped when the cache is full; scores then
run over the full capacity). A stateless `1 + (p - y) / P_BLOCK_SIZE`
reproduces the count exactly, including the `p ≡ y (mod P)` boundary, but
**loses the cap**, so `current_len` keeps growing past capacity and
`score_group_base(b, g, current_len)` overflows the fixed `G·C` request
segment into the next request's scores.

The fix is to re-assert the saturation in the derivation itself
(`decode.csl:180-185`): return 0 for `p < y`, else the quotient form clamped
to `kv_len_per_pe`. That clamp is exactly congruent with `process_kv`'s write
guard `column < kv_len_per_pe` (`decode.csl:1297`) — whenever the length
saturates, columns `0..kv_len_per_pe-1` were all written in earlier steps, so
score/exp/sum/Score@V reads stay on valid data and the request segment is
spanned exactly, with no overflow. It also reproduces origin/main's
guarded-increment saturation semantics, preserves the zero-row case, and keeps
bsz=1 equivalence with the baseline.

Generalizable form (procedural — promotion candidate): when state is replaced
by a pure function of position, enumerate every invariant the *guard around
the state update* enforced, not just the value the state held. A guard on an
increment is a clamp on the derived function; it does not survive the
translation for free.

## Evidence level

Three independent no-edit reviews of `decode.csl` (the first found the missing
clamp; two after the fix returned APPROVED, one full-scope and one narrowed to
the softmax/Score@V window). Verification is **source review plus a
compile-only gate — no device gate has been run on this change.** Alpha
scaling stays deliberately post-X-all-reduce and was confirmed unmoved; no
`comm_mod` call site changed, so the collective ABI is byte-identical to
baseline.

## Implications / next actions

- [ ] Device gate for M1b-S0 Part 1 still owed; a long-sequence case that
      actually saturates `kv_len_per_pe` is the one that exercises this clamp.
- [ ] Any future position-derived helper added to this family
      (`position_current_length`, `position_write_column`,
      `score_request_base`, `score_group_base`) must be checked against the
      same capacity invariant, since the fixed-shape request segments assume it.

## Pointers

- `models/qwen3_1p7b-decode/src/decode.csl:180-185` (saturating helper),
  `:1297` (`process_kv` write guard), `:187-192` (segment bases)
- Related: `memory/topics/decode-context-ceiling-lives-in-the-elf-and-wraps-silently.md`
  (the other silent long-sequence wall on this kernel),
  `memory/topics/decode-kv-strided-placement-and-resume-granularity.md`
- Skill `decode-gqa-max-seq-len-decode-room` covers the config-side version of
  the same capacity invariant (`max_seq_len` leaving no decode room).
