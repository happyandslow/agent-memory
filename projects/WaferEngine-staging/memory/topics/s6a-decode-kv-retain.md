# S6a-decode — PE-internal KV retain (decode kernel): implementation & verification learnings

> Curated, reusable learnings from implementing + verifying decode-side KV retain
> (M0/S6a-decode, 2026-07-15). **Plan/state live in the in-repo durable docs**
> (`milestones/M0-reuse-foundation.md § S6a`, `PROGRESS.md`) — those win on conflict.
> This note holds only the transferable engineering learnings.

## What was built (shape)

Standalone `qwen3_1p7b-decode`. Retain = on a "retain round," keep the resident per-PE
KV slab and continue decoding from its high-water mark instead of rewinding
`round_reset` to the fresh prefill length. Driven by an explicit `request_id` from a
minimal host keyed store (retain-not-discard, no eviction). Two demos:

- **chain** — N-request accumulate: round 0 fresh, rounds 1..k retain and continue from
  the growing high-water (RETAINED_LENS = −1 sentinel = "use current high-water").
- **repeat** — whole-prefix repeat: retain round truncates back to the prompt length
  (RETAINED_LENS = prefill) and re-decodes; must reproduce round 0's stream.

## Design: retain rides a widened KV-ingress meta tile

Three per-round scalars are **independent** (you cannot infer one from the others):

| scalar | role | fresh round | retain round |
|---|---|---|---|
| `plen` (prefill_len_per_pe) | how much KV to scatter (payload) | prefill | **0** |
| `decode_len` | this round's decode budget D (caps `n_steps`) | D | D |
| `retained_len` | decode START / eff_len (round_reset seeds from it) | prefill | high-water (or truncated) |

So the KV-ingress meta tile widened `KV_META_LEN` **2 → 4**: `[plen, decode_len, retained_len, pad]`.
On-device `retain_rt = (plen == 0)` — retain rounds ship a **meta-only heartbeat**
(plen=0, zero KV payload), which *is* the "don't re-ship KV" win. `round_reset` unified
on a single accessor `eff_len = retained_len_per_pe_rt`:
`n_steps = decode_len·P_BLOCK_SIZE`, RoPE + `iter_num_bank` seeded to `eff_len`.
Seam rules held: retain enters as **data** into the one `round_reset` (no forked reset);
never overload `prefill_len_per_pe_rt`; retain touches only counters+RoPE, KV scatter is
merely **gated** by `retain_rt` (not modified).

## Landmine 1 — `plen==0` meta-only heartbeat breaks switch/router relay PEs

decode's per-round advance is **coupled to the KV-ingress path** (the block PE blocks on
the meta recv), so a retain round must still send the meta heartbeat to advance — it
cannot skip the ingress send entirely. But the relay PEs
`kv_ingress_injector.csl` (`emit_scatter`) and `kv_ingress_adaptor.csl` (`relay_kv`)
**unconditionally moved one KV segment even when `n_segs_rt = D_kv·plen = 0`** — reading a
phantom `seg_len` block that the host never sent, leaving undrained wavelets on the
kv_ingress color. Symptom: **round-1 `FATAL: Attempt to remap input queue 7 ... router is
holding wavelets`** (the block PE's `kv_ingress_flush_then_resume` rebind of IQ7 from the
ingress color back to broadcast). Round 0 (fresh, plen>0) passed — proving it was the
retain path, not the meta-width change.

**Fix:** an `n_segs_rt==0` fast-path in both relay tasks that does the row-advance
(`SWITCH_ADV` / round-sync via `sync_src`/`sync_wait`) **without** moving a segment — the
"engine keeps turning (advance/heartbeat) but carries no cargo (KV segment)."
**General lesson:** any transport/relay PE that assumes ≥1 payload unit per row will break
on a legitimate zero-payload heartbeat. Check every relay for this when adding a
skip-the-payload mode.

## Landmine 2 — widening a meta tile ripples into hardcoded widths

Growing `KV_META_LEN` 2→4 required updating **hand-coded** meta widths that the SdkLayout
port sizing did NOT auto-scale:
- host `_row_u32 = Pw + C_kv·plen` → `2·Pw + C_kv·plen` (metas are now 2 u32/tile).
- injector/adaptor `num_cols` (the u32 relay count): `Pw` → `Pw·KV_META_LEN/2`.
The port/DSD sizing that referenced the `KV_META_LEN` symbol scaled automatically; the
literals did not. **When widening any metainfo, grep every reader + size-assert of that
width, not just the field's obvious consumer.** (The injector reads `plen` via
`@as(u16, meta0_buf[0])` = low 16 bits, so packing `decode_len` in the high 16 of the
first u32 is safe — it truncates it away. That "put a second value in the high half of an
existing u32" trick is only safe because the existing reader masks.)

## Verification — value-based full-distribution beats rank-based top-k

**Falsified assumption:** "device-vs-oracle top-k overlap is a valid decode pass/fail
gate." On the tiny 24-token mock vocab, top-k SET overlap sits at **~0.5 even for a
correct fresh round** — fp16/bf16 tie-breaks flip the near-degenerate #2 rank while #1
(argmax) stays put (`argmax_match=1.0`). Rank metrics are both **noisy** (an absolute
`≥0.999` gate false-fails a correct round) and **insensitive** (argmax-only misses
#2+/tail corruption → false negatives). #2 is structurally more fragile than #1: it has
two neighbors (#1 above, #3 below), either near-tie flips it; #1 has only one.

**What works:** dump the **full fp32 step-0 logits on-device via CSL `simprint`** and
compare *values* to a teacher-forced numpy oracle.
- `simprint` (SDK v2.10, `@import_module("<simprint>")`) exposes `print_f32` /
  `print_u32_hex` / `print_u32_decimal`. For exactness dump `@bitcast(u32, logit)` raw
  bits → host `np.uint32(...).view(np.float32)` (zero precision loss). Output lands in
  `<artifact_dir>/sim.log`; parse by a greppable marker (`[LOGITDUMP] r= b= x= V= : bits...`),
  not physical lines (simprint isn't line-buffered).
- The full vocab logits live in `ht_tail.csl` `partials_buf` **after the fp32 Y-allreduce
  and BEFORE the X-axis top-K merge-reduce** — sharded across the root-row X-PEs,
  `global vocab id = x_local·V_per_pe_x + v` (matches the oracle's `W_lm_head` column
  order). No single PE holds the whole vocab; reassemble on the host from the shards.
- The device does lm_head + top-K in **fp32** (not fp16) — so the divergence is from
  **upstream bf16 hidden states**, not the head. Comparison is fp32-vs-fp32.
- **Teacher-forcing:** the resident KV was built from the device's *stochastic* samples,
  so the oracle can't run its own argmax chain — it must replay the device's per-round
  sampled tokens to rebuild the exact KV, then compute each round's step-0 logits. The
  seed is **re-sent every round** (same X[0]), so only **step 0** is a deterministic
  comparison point.

**Result:** every retain round matches the oracle to **max_abs ~1.3e-4** (the fresh-round
noise floor, ~3 orders below a 0.05 break threshold; cos ≈ 0.999999). Verdict is
**relative** — a retain round is broken only if its value-diff jumps clearly above the
fresh baseline, not merely nonzero. This decisively settled "is the 0.5 top-k overlap a
bug or noise?" → noise (the full distributions agree to 1.3e-4).

See also: [[standalone-vs-integrated-kernel-parity]], [[pr14-real-serving-port-contract]],
[[csl-control-payload-mechanisms]], [[kv-cache-policy-tradeoffs]].

## 2026-07-13 pre-S6 abstraction design

Before S6a coding, five read-only digs across standalone decode/prefill and integrated e2e/pdSeparate answered whether a shared KV-management abstraction could make all three decode variants inherit retain automatically.

- KV-touching compute is identical modulo naming across the kernels: `process_kv`, attention reads, `iter_num`/`step` bank handling, RoPE advancement, and cache allocation share the same structure. e2e vs pdSeparate `decode.csl` differ only by a WIP TSC profiler; their KV difference is off-chip feeder/relay wiring, not decode-kernel semantics.
- Retain touches counters and RoPE only, never `kv_ingress_*`; west-vs-north ingress is irrelevant to retain logic. The blocker is lifecycle: integrated kernels still lack runtime-variable prefill/cached length, `round_reset`, a multi-round loop, and re-arm plumbing, so retain has nowhere to attach until S4/S5 ports that lifecycle.
- Decision: S6 remains standalone-first and seam-isolated. Retain enters as data into one `round_reset`, through one runtime-capable retained-length accessor, and touches counters/RoPE only so the later S4/S5 extraction is mechanical.
- Prefill retain is the same mechanism in a different counter: persistent non-zeroed `K_cache_bank`/`V_cache_bank`, multi-round serve loop, and `enter_request` counter reset imply a `start_chunk` warm-start plus host stream-skip path; no inverse transform, cross-PE movement, or RoPE re-derive is needed. **This prediction held** — the warm-start was built and verified on 2026-07-19; see [[s6a-prefill-warm-start]] for its defects, capacity walls, and the (k/n)² reuse-saving finding.
- Force-decode is the M2 boundary: pure retain covers resume/exact-prefix repeat on decode plus shared-prefix fanout on prefill; realistic multi-turn decode of known new tokens needs an input-token override, not a new cache primitive.

Source/drain note: `memory/inbox/2026-07-13-kv-management-abstraction-design.md`.
