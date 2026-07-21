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
