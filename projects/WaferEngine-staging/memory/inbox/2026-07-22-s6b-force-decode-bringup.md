# Force-decode bring-up: the host must OWN the forced-token sequence, and an if/else input-gate swap silently breaks color-7 balance at F>1

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured

## Situation

Implementing S6b force-decode in standalone `qwen3_1p7b-decode` (feed F known tokens
through the per-token path so `process_kv` appends their KV). Step 0 (inert seam: F
carried in KV-meta slot 3 → header → ht_tail/ht_head) landed and passed byte-identical
at F=1. Step 1 (host feeds F embeddings; ht_head uses them on forced steps; oracle
teacher-forces the forced sequence) is in progress. Two non-obvious things surfaced
while wiring the oracle and reviewing the ht_head edit.

## Finding 1 — the forced tokens are host-owned; assemble them, don't read them back from device spill

Force-decode's forced-step **device output is meaningless** (Step 1 discards the sample;
Step 2 emits a dummy). The host GENERATES the forced tokens, so it already knows them —
the correct data flow is: host builds one **distinct** forced sequence and feeds the SAME
sequence to BOTH the device (as x_stream embeddings) AND the numpy oracle. The device's
forced-step south spill is never trusted.

Two consequences that make this not optional:
- **Multi-round retain-chain oracle correctness REQUIRES it.** When round k+1 retains
  round k's KV, the oracle rebuilds round k+1's prefix from round k's tokens. At forced
  positions it must use the KNOWN forced tokens, NOT the garbage device sample at that
  step — otherwise the teacher-forced prefix diverges and the whole comparison is invalid.
- **It kills the "repeat the seed F times" placeholder.** Repeating the seed makes the
  oracle need a `pad_force_decode`-style hack (repeat first sample fdl times) that is both
  buggy (fdl referenced before it's bound per-round) and semantically muddy. Generating
  distinct tokens (e.g. `forced_tok[f] = (retained_len + f) % vocab`) and feeding one copy
  to device+oracle removes the hack entirely and exercises position-dependent bugs a
  repeated token would mask.

Token VALUES are arbitrary for a mechanism demo (only device==oracle consistency matters),
so no explicit token list in config is needed — F (`FORCED_DECODE_LENS`) plus a
host-side deterministic rule is enough. Compare only at **step F-1** (first free token's
logits; depends on all forced KV) — one dump per round, not per forced step.

## Finding 2 — an if/else input-gate swap silently drops the token drain → hang at F>1, invisible at F=1

ht_head's per-step input gate is today `if (ht_step == 0) { read pre_embed_x } else {
drain token color; gather }`. Changing it to `if (ht_step < F) { read pre_embed_x } else {
... }` LOOKS right but is a **color-7 (token) producer/consumer imbalance**: forced steps
1..F-1 now take the `if` branch and **skip the token drain**, while ht_tail (unchanged in
Step 1) still emits a token north every step 0..N-2. Result: F-1 undrained wavelets
accumulate on tok_iq each round → backpressure stalls ht_tail OR the residue is misread as
the next round's header. Same family as the S6a round-1 IQ7 FATAL (zero-payload heartbeat)
— see [[s6a-decode-kv-retain]].

**Why it passes review-by-running:** at F=1 (the inert default), `ht_step < 1` ≡
`ht_step == 0`, so it compiles, is byte-identical, and every existing config passes. The
imbalance only bites at F>1 — which no config exercised yet. Classic "new per-request
count hits an implicit old default; silent at the default."

**The discipline (procedural — promotion candidate):** when adding a per-request count
dimension to a lock-step step loop, a shared-fabric-color op must stay **additive**, not
restructured. Correct Step-1 form: keep `if (ht_step == 0)` for the seed, keep the token
drain running EVERY step (its result discarded on forced steps), and ADD a separate
`if (ht_step < F) overwrite embed from pre_embed_x` after the gather. Producer==consumer
count on color 7 is then unchanged → zero hang risk. Dropping the drain (Step 2's
optimization) is only safe if ht_tail simultaneously stops emitting on forced steps
(the F-1/F mirrored boundary) — do that as a separate, deliberate step, never as a
side effect of the input-gate edit.

## Pointers

- Plan: `docs/superpowers/plans/2026-07-21-m0-s6b-force-decode.md` (three-step staging)
- Design capture: `2026-07-21-s6b-force-decode-design.md` (mechanism, F encoding, boundaries)
- Related: [[s6a-decode-kv-retain]] (zero-payload heartbeat / IQ7 FATAL — same color-count family)
- Code: ht_head input gate `ht_head.csl:307-345`; ht_tail north emit `ht_tail.csl:1388`;
  forced-token build/oracle in `launch.py` + `host/oracle_fp16.py::numpy_oracle_retain_step0`.
- Minor (not captured, low durability): `@mov32(dest_dsd, i32_value)` accepts a scalar
  immediate source (builtins.md) — I asserted it needed a DSD and was wrong; verify CSL
  builtin signatures against builtins.md, don't assert from memory.

## Update 2026-07-23 — Step 1 landed + sim-verified (F>1), and a resolved-in-code detail

The 3 bugs above were all fixed and **S6b Step 1 is end-to-end sim-verified for F>1**:
`test_sim_2x2block_kv_forcedecode.json` (round 1 = retain reuse-16 + force-decode F=4 distinct
tokens `[seed,1,2,3]` + free-decode) matches the teacher-forced oracle at **step F-1** to
`max_abs 9.8e-5` (noise floor). **No hang** — the additive ht_head (keep `==0` seed + drain
token every step + ADD `ht_step<F` pre_embed_x overwrite) preserved color-7 balance, confirming
the earlier if/else-swap hazard was the right thing to avoid.

Two things worth keeping:

- **The forced-token sequence is a TOKEN×BATCH 2-D thing, not 1-D.** `token_ids` (len bsz) is the
  BATCH axis (one seed per request/lane); force-decode adds a TIME axis (F steps). Full input is
  `forced_tokens[F][bsz]`, and `token_ids` is its step-0 row. Generation: step 0 = `token_ids`
  (keeps F=1 inert), steps 1..F-1 = a deterministic in-vocab rule (`[i % vocab_size]*bsz`), the
  SAME array fed to BOTH device (packed to x_stream) and oracle (W_E lookup). Do NOT try to reuse
  the device's *packed* `x_step_buf_u32` in the oracle — it's the wire layout (u32, column-
  transposed); the oracle needs `(bsz,dim)` bf16, so share the token-ID rule, not the buffer.

- **When you move a device dump point, grep for EVERY consumer's step index — a stale one is a
  silent step-mismatch, not just a stale label.** Moving the logit dump from step 0 to F-1 fixed
  the value-based verifier, but a SECOND consumer (the rank-based Pass-1 diagnostic) still read
  the device's step-0 top-k (`per_round_topk_args[k][0]`) while the oracle now returned F-1 —
  comparing two different steps. It only "passed" via the relative-baseline logic. Fixing it to
  `[fdl_k-1]` moved round-1 overlap 0.5→1.0 (now step-aligned). Same lesson family as "new
  per-request dimension hits an implicit old default": when F-1 replaces a hardcoded 0, the 0 can
  hide in more than one place.

**Verification methodology note (reusable):** distinct forced tokens (not seed-repeat) are what
make the test meaningful — a repeated token can't distinguish "KV appended at position L+2" from
"at L+0", so it masks position/RoPE/iter_num bugs. Same value-based full-distribution method as
S6a, but the deterministic comparison point is step F-1 (first free token, depends on all forced
KV), = step 0 when F=1.
