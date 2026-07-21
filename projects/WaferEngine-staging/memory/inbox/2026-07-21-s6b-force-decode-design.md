# S6b force-decode: the decode kernel already force-decodes one token/round, and skipping tail-sample opens layer pipelining

Date: 2026-07-21 · Repo: `WaferEngine-staging` (S6b design, no code yet)

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured

## Situation

S6b needs a forced-token input path in standalone `qwen3_1p7b-decode`: feed a known
token (not a sampled one) so `process_kv` appends its KV, to build multi-turn
(retain prefix → force-decode new turn's known tokens → free-decode reply). The
question was how big a change this is and where the forced token enters.

## The kernel already force-decodes exactly one token per round

Decode step input is forked: **step 0** consumes a host-seeded, already-embedded X
vector (`launch.py` sends `host_x_f16 = W_E_full[token_ids]` once per round via
`x_stream` → demux → `pre_embed_x_color`; the diagonal PE drains it at
`ht_head.csl` step-0, skipping on-chip embed gather). **step ≥1** is autoregressive
(ht_tail samples → `tok_bcast` north → ht_head embeds). So "feed a known token"
already exists — it is hardcoded to exactly 1 token, at step 0. **S6b = parameterize
that count to F.** `forced_len = 1` is today's behavior → a free inert no-op baseline
(same shape as S6a's `retain=0` / `start_chunk=0`), with no dead path to add.

`F` unit is **token**, not block: it indexes the global step loop (`n_steps`), which
is unsharded — unlike `retained_len`/`prefill_len` which index per-PE cache columns
(block units). Making F block-aligned would force force-decode granularity to
`P_BLOCK_SIZE` (=256 on device) → useless for real multi-turn. Keep F in tokens.

## Design decision (user chose "option 3"): tail skips logits on forced steps

Two shapes were on the table. Option 1: ht_head overwrites the gathered embedding
from `pre_embed_x` on forced steps (fabric shape unchanged, immune to wavelet-count
and odd-extent traps, but keeps the per-step blocking read). **Option 3 (chosen):**
on forced steps ht_tail skips the whole logits/sample pipeline and emits nothing
north; ht_head must therefore know F on every column and NOT drain the token color
(else it blocks forever — same family as S6a's round-1 IQ7 FATAL / wavelet-count
mismatch). Route repaint is NOT needed: the tail step loop is a closed Y→X→Y
round-trip (`write_X_routes_tail` at Y-allreduce↔X-topK, `write_Y_routes_tail` next
step); skipping the whole `if (tail_my_py == root_2nd_phase)` block atomically
leaves routing in the Y resting state.

## Why option 3 matters beyond saving lm_head: it opens layer pipelining [unverified]

Decode blocks are a layer pipeline with **no structural serial barrier**
(`inter_block_send_z`/`recv_x_sync` are plain synchronous `@fmovh`, block only until
fabric accepts, not until downstream finishes). Normal decode is serial ONLY because
of ht_head's blocking read waiting for ht_tail's sample — a full round-trip bubble.
Option 3 skips that read on forced steps, so ht_head can emit X continuously and the
layer pipeline fills. **[unverified] force-decode may therefore be FASTER per token
than normal decode** — a structural gain, vocab-independent, measurable in sim (not
the lm_head saving, which is negligible at vocab=24). Option 1 structurally forbids
this because it keeps the blocking read.

Three things NOT verified (measure with existing TSC before claiming): actual
overlap depth (bounded by block count / queue capacity / backpressure), whether
blocks are truly disjoint PE sets, and whether ht_head can really run F steps ahead.

**Implication to route to M2:** R* uses "force-decode step ≈ normal decode step". If
force-decode pipelines, that **systematically underestimates force-decode** — and the
bias favors the in-place force-decode direction the ROADMAP already prefers. But do
not over-extrapolate: prefill's speed comes from in-layer token batching (arithmetic
intensity); force-decode only removes the round-trip bubble, per-token matvec
efficiency is unchanged, so it should land between decode and prefill speed.

## Plan finalized — concrete design (2026-07-21, later same session)

Reviewed the full token feedback path and host round loop (file:line anchors below),
converged the design, wrote the plan file. Decisions that clear the bar:

- **F carried in KV-ingress meta slot 3 (currently a hardcoded pad = 0), value = F
  directly, default 1.** No `-1`/`+1` storage trick and no config migration: the meta
  is built in ONE host Python line (`_repack_kv_band`, `launch.py:2459`,
  `meta_tile=[plen,dlen,rlen,0]`) and the device does not peel slot 3 today, so the
  host write and the device peel are both added in Step 0 — consistency is ours to
  define. `F=1` is not a pad hack, it is the semantically-correct inert value: the
  F-sequence's **last (transition) step** (host input + sample + emit) is byte-identical
  to today's single decode-start step; `F=1` = "sequence with only the transition step"
  = today. (Rejected an earlier `store F-1, device +1` proposal — solved a non-existent
  compatibility problem.)

- **Load-bearing off-by-one — the two gates are NOT the same F.** Because sampling at
  step k produces the INPUT for step k+1: ht_head input gate reads `pre_embed_x` for
  `ht_step < F` (F host tokens), ht_tail skips sample/emit for `tail_step < F-1` (F-1
  pure-forced steps) and samples from step F-1 (whose output = first free token). Color-7
  (token) balance: emit `{F-1..N-2}` ↔ drain `{F..N-1}`, N-F wavelets each. Writing both
  gates off the SAME peeled F but mirrored at F-1/F is the whole correctness argument;
  a same-`<F` predicate on both sides (my first sloppy statement) is wrong and hangs.

- **N-header widened to explicit 2-wavelet `[N, F]`, NOT a bsz lane.** F reaches ht_tail
  and ht_head via the existing result-header→N-header chain (`decode.csl:1770-1773` →
  ht_tail `:1303-1311` north → ht_head `:296-298`). The north header is bsz-wide-replicated
  today; packing F into lane 1 collapses at bsz=1 (lesson: new per-request scalar hits an
  implicit old default). Use a dedicated 2-wavelet DSD.

- **Three staged steps, one rewrite point.** S0 inert (F=1 byte-identical) → S1 correctness
  (host feeds F embeddings, ht_head diag overwrites embed from `pre_embed_x` for `ht_step<F`,
  **ht_tail unchanged**, token drain still every step → zero color-7 risk) → S2 pipelined
  (ht_tail skips compute for `tail_step<F-1`, dummy-zeros south to keep host receive count
  `==n_steps`, and `ht_head.csl:309` token drain gets an `ht_step>=F` guard). The token-drain
  guard is the ONLY line S1→S2 rewrites (unconditional→conditional); everything else is
  additive. Rollback S2→S1 = drop that guard.

- **demux needs no change** — it is a per-cycle store-and-forward pump that already
  self-re-arms (`demux.csl:136-144`; the file-head "single-shot" comment is stale). Host
  just pushes F X-vectors instead of 1; backpressure paces them. Grep the x_stream
  total-wavelet quota (sized by NUM_ROUNDS×1 X) → must scale to F_max.

- **Verification:** value-based full-distribution vs teacher-forced oracle (S6a method),
  but dump logits at `tail_step == F-1` (was step 0) — the first free token's logits depend
  on all forced KV, so they are the aggregate correctness signal.

## Pointers

- Plan: `docs/superpowers/plans/2026-07-21-m0-s6b-force-decode.md`
- Builds on: [[s6a-decode-kv-retain]] (retain composes with force-decode in one round)
- Token feedback path: sample `ht_tail.csl:1085,1374`; north emit `:1385-1391`
  (`tok_bcast_color` id 7); ht_head receive `:309`; seed path `ht_head.csl:301-304` +
  `launch.py:2546`.
- Routes to M2 / `GOALS §7`: force-decode-may-beat-plain-decode (pipelining) [unverified].
