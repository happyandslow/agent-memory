---
summary: M2-S2 — porting force-decode from the standalone decode lineage onto the pr14 pdSeparate line, verified end-to-end on real WSE-3. Two invariants the source lineage does not have, a correctness criterion built without an oracle, the measured forced-token cost (13.50%), and the controlled payload change that falsified the H2D "bandwidth".
tags: [waferengine-staging, m2, force-decode, pdseparate, cs3-cluster, measurement, correctness, kv-cache, porting]
---

# M2-S2 — force-decode ported to pdSeparate, and what the port taught

Worktree `/home/lexu/we-m2bench`, branch `lexu/staging/m2-benchmark` (snapshot
`a3a509c` + S1), model `models/qwen3_1p7b-e2e-pdSeparate`. Real WSE-3 (EPCC CS-3),
2026-07-30. **Uncommitted** — Le owns commits. Plan + full evidence index:
`we-m2bench/M2-S2-force-decode-port-plan.md` (revision 2, ~815 lines).

Plan/state live in the durable docs (`ROADMAP.md` / `PROGRESS.md` /
`milestones/M2-tiering-cost-model.md`) and win on any conflict. This topic keeps
only the transferable learnings. Related: [[s6b-force-decode]] (the source
mechanism), [[h2d-host-device-bandwidth]] (contradicted — see below),
[[standalone-vs-integrated-kernel-parity]], [[m2-s1-measurement-lenses]].

## 1. A cross-lineage port is a re-derivation of invariants, not a transplant

The mechanism was "known and merged" on `kv-feature`. It still ported cleanly
only because two invariants that **do not exist on the source lineage** were
found *before* writing code. Both would have been expensive to find afterwards.

**(a) pdSeparate runs one extra terminator step per round.** `decode.csl`,
`ht_tail.csl` and `ht_head.csl` all loop `< n_steps + 1`; at `ht_step == n_steps`
HT_head floods `STOP_SENTINEL_F16` and **breaks without draining**. The colour-7
(`tok_bcast_color`) emit/drain accounting therefore had to be re-derived for that
shape rather than copied:

| | ht_tail emits | ht_head drains |
|---|---|---|
| baseline | 1 header + `[0, N-2]` = N | 1 header + `[1, N-1]` = N |
| with F | 1 header + `[F-1, N-2]` = N-F+1 | 1 header + `[F, N-1]` = N-F+1 |

The terminator neither emits nor drains, so it stays balanced; requires
`1 <= F <= N`. **Getting this wrong is a silent device deadlock** — no error, no
log line, ~14 minutes per attempt to discover.

**(b) The sampler draws from a RUNNING PRNG.** `ht_tail.csl` calls
`random.random_f32(0.0, 1.0)` once per `tail_sample_token`, re-seeded once per
round, and the serve config is `temperature 0.6 / top_p 0.95` — genuinely
stochastic. Force-decode's whole point is to **skip the tail compute**, which
skips that draw, leaving the stream `F-1` draws behind.

> **A completely correct implementation would therefore fail its own correctness
> criterion**, with the symptom "the tokens diverge" — which points the
> investigation at the KV path, the colour balance, or RoPE. At a bug that does
> not exist.

Fix: perform and discard exactly one `random_f32` on the sampling PE in the
skipped branch. Two `@random16()` LFSR reads, ~10–20 cycles, on one PE out of
524,288, off the forced step's critical path — the pipelining gain is untouched.
Call `random_f32` (not `@random16` twice) so the alignment survives a library
change to the draw count.

**One thing was *easier* than the source lineage predicted:** pdSeparate seeds
step 0 with a **token id** and does the `W_E` gather on-chip, where the standalone
fed a pre-embedded X vector. Forced tokens are therefore just token ids.

## 2. Building a correctness criterion when the line has no oracle

pdSeparate has **no simulator path** (`simulator_used` hardcoded false, no
`run_sim.sh`/`launch_sim.py`) and **no numpy oracle**. S6b's gate — sim `simprint`
full-fp32 logits vs a teacher-forced oracle, `max_abs 9.8e-5` — was never
available here, and `trace_sha256` cannot be the gate either because output
changes by construction at `F > 1`.

**Criterion used: self-teacher-forcing.** Free-decode, record the trace, then
force-decode the model's *own* tokens and require the continuation to be
bit-identical. No oracle needed; the model is its own reference.

It is sharper than it looks. Sampling is stochastic over a top-20 / top-p-0.95
nucleus, so any perturbation of the logits changes the softmax, changes where
`acc >= u` lands, and diverges the trajectory. Equality over **10,067 tokens ×
8 requests** is a chaotic-system test, not argmax agreement.

Index mapping that makes it work: step 0's input is the host seed; step 0 samples
`ids[0]`, which becomes step 1's input. So step `s >= 1` consumes `ids[s-1]`, the
forced inputs for `F = m` are `ids[0 .. m-2]`, and the first real sample is at
step `m-1`. **Compare `ids[m-1:]`.**

**Hard constraint discovered while auditing the gate:** `done_flag` is set *inside*
`tail_sample_token` — EOS detection, pad substitution and the early-stop cascade
all live there — so a skipped step never updates it. **No forced token may be an
EOS or pad id.** Measured aside: on `mtbench8` the constraint can never bind,
because with `enable_early_stop = 1` the EOS id is overwritten by `STOP_TOK`
*before emission*, so EOS appears **zero times** in 10,571 sampled ids despite
`halted_eos: True` on all 8 requests. The in-source comment "The EOS was emitted
on its own step" is wrong when early stop is enabled.

## 3. "Inert" means the output is unchanged — not that the cycle count is

The Step-0 gate was originally "zero device-classified `timing.json` leaves
outside ±0.05%". **It cannot be met by construction**, and running it is what
showed why: ±0.05% is a **run-to-run** bound for a **fixed binary**; Step 0
compares **two binaries**. Requiring a changed binary to reproduce cycle counts to
run-to-run precision is requiring the compiler to emit identical code.

Measured shift: **−0.044%/token**, systematic across all 8 rounds (−234 to −253
cycles/token, band 0.005%) — and *faster*, despite the port adding two
comparisons per step, so it is code layout, not semantics. Scale for comparison:
two same-binary pairs give **−0.0001%** (±1 cycle/token — the device is
essentially perfectly deterministic) and **+0.0219%** (a whole-run offset).

⇒ **Inertness gate = `trace_sha256` bit-exact + placement unchanged
(`colors.json` / SIM_PORT_MAP / router-warning set) + liveness.** Timing is
checked at the scale that would change a conclusion (~1%), and the systematic
shift is *reported*, not gated.

## 4. Measured: the forced token costs 13.50% of a free one

| | cycles | µs |
|---|---|---|
| free token | 556,354 | 654.53 |
| saving per forced step | 481,257 | 566.19 |
| **forced token** | **75,097** | **88.35** |

Setting: Qwen3-1.7B real HF weights (rev `70d244cc`), pdSeparate on one CS-3/WSE-3,
`Pw 512 × Ph 1024` = 524,288 PE, 2×4 blocks, `max_layers_per_block 4`, batch 1,
`mtbench8_s2`, `F = 64`, **n = 1**, real hardware.

**Why it is a measurement and not two anchors subtracted:** `steady_tokens` is
identical per round in both runs (same step range), and the per-round saving is
**constant at 22.06–22.20 M cycles (0.61% spread) across rounds of 461–3364
steps** — a per-forced-step constant, which rules out a context-length effect.

| source | forced/free | setting |
|---|---|---|
| standalone decode | 11.7–12.0% | mock weights, 28L/8blk |
| **pdSeparate** | **13.50%** | real weights, 28L/2×4blk |
| `max_lpb / n_layers` | 14.29% | `4/28`, identical on both |

Both below the prediction, within 1.8 points of each other, on different weights
*and* different block grids ⇒ **the layer-pipelining account survives**.

## 5. ⚠️ The H2D "bandwidth" is not a bandwidth — this contradicts an existing topic

[[h2d-host-device-bandwidth]] and M2-S1 record the KV ingress at **0.7726 GB/s
aggregate**, derived as one payload ÷ one span. Step 0b ran the **first controlled
payload change** on that path (widening the KV-meta tile 2→4 slots):

- payload **+5.882%** (35,651,584 → 37,748,736 B per round, exactly 1/17)
- device-TSC span **+0.0085%** (46,145.392 → 46,149.306 µs)
- ⇒ the extra **524,288 B/band cost 3.914 µs = a marginal rate of 134 GB/s**,
  **12× the 11.43 GB/s H2D physical ceiling and 655× the average**

The bytes provably crossed: the relay's `metablk` DSD extent is a compile-time
`num_cols - 1` u32 per row, so a short host payload starves the relay and hangs
the round — and the round completed.

⇒ **46.146 ms is a span that barely moves with payload.** Dividing bytes by it is
not a rate, and pricing the reload lane as `bytes ÷ 0.7726 GB/s` **overpredicts
the marginal cost of moving more data** — biasing the cost model *against*
offload, the opposite of the conservative direction.

Where the 46.1 ms actually goes is **not answered and must not be guessed.** The
experiment that would separate per-op from per-byte varies the **KV** bytes rather
than the meta: a prompt with `plen_per_pe > 1`, or the existing `KV_DSD_SEG_MAX`
config override which forces segmentation at *constant* payload.

**This is now the same diagnosis on three independent paths** — the on-chip
prefill→decode move (1.803 GB/s, 2.2× below one link), the M3 park-band analysis
(a fixed ~4.54 µs per store-and-forward step carrying 16 B, wire idle 99.91%), and
now H2D ingress. A per-operation cost dominating a per-byte cost *everywhere* is
an architectural property of this codebase's movement idiom, not three separate
defects.

## 6. Transferable lessons

- **A rate is only a rate if you have varied the numerator.** S1 divided one
  payload by one span. The first time anyone changed the payload, the span did not
  follow.
- **Test the instrument on a known-good pair before trusting it.** The first
  timing-gate script classified `.tsc.`-prefixed *host* fields (`kv_handoff_s`,
  `recv_s`, `decode_wall_s`) as device readings and **failed S0's own two
  bit-identical runs**. Reclassifying from the baseline's 43 `.tsc.` leaves and
  re-validating reproduced the documented ±0.0268% jitter independently.
- **A checker that refuses is worth more than one that copes.** C1's first run
  came back **REFUSED, not PASS or FAIL**: its `len == generated_tokens + 1`
  invariant was written against pre-A+ semantics while a sibling change had just
  redefined `generated_tokens` to exclude the `F-1` forced positions. Two of our
  own changes disagreed by exactly `m-1` in every request. A checker that had
  compared "whatever slice it could" would have compared a shifted region and
  reported a plausible number.
- **Prove the checker can fail before trusting its PASS.** Six negative controls,
  the load-bearing one being a deliberately corrupted bundle that must FAIL with
  the *exact* `first_mismatch` index.
- **Never splice host-known values into a device trace.** `trace_sha256` is
  computed from `sampled_ids`; substituting the forced tokens would make two runs
  with different device behaviour agree *by construction* on the spliced span
  while the artifact still looked like a measurement. Provenance was split
  instead: raw trace untouched, `results.json` gains `forced_decode_len` /
  `forced_prefix_token_ids`, and the residual became a *positive* check that the
  skip gate fired.
- **`pgrep -f "<pattern>"` matches the command line that contains the pattern —
  including your own.** A launch guard reported "already running" forever until
  the pattern was written `[l]aunch_device.py`. Silent, and it looks identical to
  the guard working.
- **`_stage_request` renames any `--request` file to the fixed name
  `request.json` on the worker**, so the worker command line cannot tell an `F=1`
  run from an `F=64` one. Establish `F` from `results.json`, never from the log.
- **`rsync --delete` to the CS-3 mirror would delete the remote run outputs.** Use
  an explicit `--files-from` list; verify with md5 afterwards.

## 7. Operational notes (EPCC, 2026-07-30)

- **6 serve attempts, 3 completed.** Every failure was the EPCC ingress gRPC
  **502** (`10.27.24.65:443`, `content-type: text/html`, thrown from
  `sdk_shutdown`); none implicated the port; `csctl get jobs` empty after each, no
  orphan jobs. Consistent with the recorded ~50% rate.
- **A cheap health probe exists:** `curl -k https://10.27.24.65:443/` returns
  **404 when healthy** (proxy up, no handler for `/`) and **502 when the upstream
  is down**. Good enough to gate an automatic relaunch.
- **A new store does not need a full build if only the decode side changed.**
  Pre-copying the prefill + tokenizer artifacts from a compatible store and running
  `--build-phase decode` took **4 min 56 s** instead of ~20 min; with both phases
  present the build rewrites `build_manifest.json`, so the reload freshness gate
  passes. Legitimate only when `src/prefill/**` and `launch_prefill.py` are
  byte-unchanged and the config differs solely in decode-side keys.
- `--reuse-prefill-from` does **not** support cross-config reuse: `_resolve_reuse_store`
  requires the source directory to be named after the *target* config.

## Update 2026-07-31 — the EOS/pad constraint now has a host-side guard

The hard constraint recorded above (**no forced token may be an EOS or pad id**, because `done_flag`
is set inside `tail_sample_token` and a skipped step never calls it) was **unenforced**: the host
checked only the *length* of `forced_tokens`, never its contents.

An independent review flagged it while reviewing E9. A guard now runs in `_serve_loop`
(`launch_decode.py`), **once, before any round starts**, rejecting any forced token in
`{eos_token_ids} ∪ {pad_token_id}`.

Why it matters more than "the round won't halt": a forced EOS does not merely fail to stop the round —
it produces a **normal-looking forced-segment measurement**. That is wrong data that reads as valid,
which is worse than missing data. Checked up front because discovering it the other way costs ~14
minutes of wafer time.

⚠️ **This also retroactively kills a plan that was briefly on the table for E9** — "make the last
forced token an EOS so generation stops right after the forced segment", floated as the zero-code
alternative to adding a TSC. It was not merely unproven; it is forbidden by this constraint. Recorded
so it is not proposed a third time. See [[e9-forced-segment-tsc]].

(Latent in practice today: with `enable_early_stop = 1` the EOS id is overwritten by `STOP_TOK` before
emission, so EOS appears zero times in 10,571 sampled ids. The guard is for the fixtures that would
have tried it deliberately.)
