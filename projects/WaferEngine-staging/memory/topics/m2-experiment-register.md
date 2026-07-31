# M2 · Experiment Register

> **What this document is.** The single index of every M2 experiment: what it asks, what it plots, what
> data it uses, and what it found. **Chapter 1 is the table** — read it to see where we are.
> **Chapter 2 is the results**, one section per row, in the same order.
>
> This replaces the chronological tracker as the place to look up progress. The old tracker
> (`topics/m2-s3-experiment-tracker.md` / ContextBase) is kept only as a **narrative of how conclusions
> were reached and overturned**; it is not the index.
>
> **Naming.** Experiments are `E<n>`. Old `S<n>` subtask ids are given in the table for continuity, but
> `E<n>` is canonical from now on.

---

# Chapter 1 — The experiment table

## 1.1 Done

| ID | Name | What it establishes | x-axis | y-axis | Data | Status |
|----|------|--------------------|--------|--------|------|--------|
| **E1** | Baseline reproduction *(S0)* | our numbers match the upstream pr14 line, bit-identical | — (table) | — | `mtbench8`, real WSE-3, n=2 | ✅ |
| **E2** | Ingress timer *(S1)* | a device-TSC pair on the KV ingress adaptor; **the rate it produced was later falsified** | — | — | `mtbench8` | ⚠️ superseded by E5 |
| **E3** | Force-decode port *(S2)* | force-decode works and is token-exact; cost of one *forced* token | — (single point) | — | `mtbench8`, `F=64` | ✅ |
| **E4** | Ingress payload discriminator *(S30 run1)* | **does** H2D KV load time depend on bytes at all? | payload (mixed within one run) | `spread_pct` of the round span | `s30_sweep`, 1 run × 8 rounds | ✅ |
| **E5** | **Ingress payload curve** *(S30 run2)* | the H2D reload cost model | KV bytes (1→32 chunks) | device-TSC ingress span (ms) | `s30_bin{0256..8192}`, 6 runs | ✅ |
| **E6** | Prefill egress payload curve | how **prefill's own** KV→host path scales | KV bytes (1→32 chunks) | `per_req_kv_egress_ms` | same 6 runs, free | ✅ |
| **E7** | Free-decode cost vs context | `f(pos)` — the compute baseline every lane is priced against | context position | µs per token | same 6 runs, free, n=22 | ✅ |
| **E8** | Long-context correctness | does output stay sane to ctx 20,480? | generated position | distinct-4-gram | same 6 runs, free | ⚠️ **inconclusive** |

## 1.2 Planned — the three-lane race

**The scenario, fixed.** One request is evicted from the decode kernel, then resumes after new context
arrives. Modelled on a long-running coding-agent session. Three regions, each independently varied:

| region | meaning | assumed state at resume |
|--------|---------|------------------------|
| `L_hist` | everything said before this turn | **KV already in host DRAM** (computed in earlier turns) |
| `L_new` | the newly arrived context — user message, tool result, sub-agent return | **not yet computed** |
| `L_gen` | tokens generated after resume | held small and fixed so it cannot confound |

**The three lanes**, exactly as posed:

| lane | what it does at resume | cost structure |
|------|-----------------------|----------------|
| **A · rebuild everything** | KV was discarded at eviction. Force-decode all of `L_hist + L_new` in decode | `Σ f_forced(pos)` over `[0, L_hist+L_new]` — no transport |
| **B · reload + rebuild the delta** | Load `L_hist` KV from DRAM into decode, then force-decode only `L_new` | `ingress(L_hist)` + `Σ f_forced(pos)` over `[L_hist, L_hist+L_new]` |
| **C · compute the delta in prefill** | Give prefill the `L_hist` KV, have it prefill `L_new`, send the delta KV back, load the whole thing into decode | `move(L_hist→prefill)` + `prefill(L_new ǀ L_hist)` + `move(delta→decode)` + `ingress(L_hist+L_new)` |

| ID | Name | What it establishes | x-axis | y-axis | Data | Status |
|----|------|--------------------|--------|--------|------|--------|
| **E9** | **`f_forced(pos)`** | does a *forced* token cost more as context grows, the way a free one does? **E3's 88.35 µs was measured at `F=64` on short contexts and may not survive `F=8192`** | force-decode position | µs per forced token | fabricated session, `F` swept | ⬜ **must precede E10** |
| **E10** | **Lane A vs Lane B** (resume latency) | the first **resume-latency** boundary: at what `L_hist` does reloading beat rebuilding? | `L_hist` | total resume latency (ms), one line per lane | fabricated session, `L_new` fixed then swept | ⬜ |
| **E11** | **Full re-prefill baseline** | re-prefill `L_hist+L_new` from scratch and ship all KV — a **measurable substitute** for lane C, not lane C, and conclusive in one direction only | `L_hist+L_new` | total resume latency (ms) | fabricated session, ≤ 8,192 | ⬜ |
| **E12** | Prefill-side KV ingestion | **a build, not a measurement** — prefill currently has egress only, so true lane C does not exist | — | — | — | ⬜ needs decision |
| **E13** | Decode-side KV egress | **a build** — the offload half of lane B. Needed for the *recurring* cost; E10 assumes DRAM already holds `L_hist` | — | — | — | ⬜ needs decision |

## 1.3 What is measurable today, and what is not

This is the honest boundary, and it shapes every plan below:

```
prefill produces KV ──[E6: egress, measured]──> host DRAM ──[E5: ingress, measured]──> decode
                                                                                          │
decode produces KV ──────────── ✗ no path exists (E13) ✗ ────────────────────────────────┘

host DRAM ──────────── ✗ no path into prefill (E12) ✗ ────────────> prefill
```

⇒ **Lane A and Lane B are measurable now. Lane C is not** — only a substitute for it (E11).
⇒ E10 measures the **resume** cost only. The **eviction** cost (decode→host) needs E13.

---

# Chapter 2 — Results

## E1 · Baseline reproduction ✅

Real WSE-3, `pdSeparate`, `serve_2x4_8k20k`, real weights, n=2. Every one of 242 `timing.json` leaf
fields reproduces upstream to ≤0.02%; all deviation is host-side. Decode steady **654.95 / 655.10 µs**,
prefill span **56.91 ms**, egress **23.49 / 23.56 ms**.

⚠️ Read only `agg_steady` / `per_round[]`. Everything in `tsc.*` outside `per_round[]` describes the
**last round only** (3.4% error on the headline `tok_per_s`).

## E2 · Ingress timer ⚠️ superseded

Added a device-TSC pair because **no host-side timer on this SDK can see the H2D wire** (`task_wait` on a
`nonblock` send reports 51.15 GB/s = 4.5× the physical ceiling). Reported 0.7726 GB/s aggregate.

**That number was not a rate.** The marker is correctly placed; the *divisor* was wrong — it was a single
payload point, and the span barely moves with payload in that region (E5 explains why: it is the flat part
of a hockey stick). E5 supersedes it; the true marginal is **4.13× larger**.

## E3 · Force-decode ✅

`F=64`, 8 requests, **10,067 tokens bit-identical** against the free-decode reference. Skip gate proven
active. **One forced token = 88.35 µs = 13.50% of a free token.**

⚠️ **Measured at `F=64` on short contexts only.** Whether this holds at `F` in the thousands is **E9**,
and E10's whole comparison rests on it.

## E4 · Ingress payload discriminator ✅

One run, 8 rounds spanning 1→32 chunks. Pre-recorded predictions: per-step model → `spread_pct ≈ 0.005%`;
per-byte model → `≈ 2,756%`. **Measured: 243.834%.** Both wrong; ingress *is* payload-dependent but not
proportionally. Its two-point fit (`35.55 ms + bytes/0.8902 GB/s`) was later shown to be the wrong shape.

## E5 · Ingress payload curve ✅ — **the main transport result**

Six runs, all rounds within a run at one payload. `band_bytes` matched the code-derived value exactly in
every bin; noise floor `spread_pct` 0.001–0.003%.

| `L_p` | chunks | MB/band | ingress ms | marginal µs/MB | marginal GB/s **per band** |
|---|---|---|---|---|---|
| 256 | 1 | 9.4 | 46.150 | — | — |
| 512 | 2 | 17.8 | 46.236 | 10.4 | 96.6 |
| 1,024 | 4 | 34.6 | 56.141 | 590.4 | 1.694 |
| 2,048 | 8 | 68.2 | 85.684 | 880.5 | 1.136 |
| 4,096 | 16 | 135.3 | 169.891 | **1,254.8** | **0.797** |
| 8,192 | 32 | 269.5 | 338.266 | **1,254.5** | **0.797** |

**Shape: a hockey stick.** A flat ~46 ms floor that ignores payload below ~2 chunks, a knee, then a
straight line through the origin:

```
above 8 chunks:  t = 0.18 ms + bytes / 0.7966 GB/s-per-band     R² = 1.000000
```

**The marginal saturates** — two independent doublings return the same value to 0.02%.
**0.7966 GB/s per band = 3.186 GB/s aggregate** (there are 4 bands; `4 × band_bytes` = 32 MiB KV + a
metadata term that tracks `KV_META_LEN` exactly).

⚠️ **A pre-recorded prediction was refuted here.** A power law fitted to the first five points at
**R² = 0.999473** mispredicted the sixth by **+27%**; "carry the last marginal forward" was exact to 0.0%.
Three successive descriptions of this curve (affine → power law → hockey stick) were each the best fit to
a *truncated* dataset. **In-range fit quality carried no information about extrapolation.**

**Contrast with E7**, which matters more than either result alone: E7's linear model, fitted over
~600–2,000, extrapolates to 20,480 — a **10× reach** — within **+2.9%**. The difference is not sample
size; it is that E7's shape is derivable from mechanism (attention scans a KV cache growing by one token
per step) while E5's shape was read off the data.

## E6 · Prefill egress payload curve ✅ — **and it does not transfer to decode**

| chunks | payload | `per_req_kv_egress_ms` | average | marginal |
|---|---|---|---|---|
| 1 | 32 MB | 23.56 | **1.424 GB/s** | — |
| 2 | 64 MB | 74.73 | 0.898 | 0.656 |
| 4 | 128 MB | 181.79 | 0.738 | 0.627 |
| 8 | 256 MB | 458.56 | 0.585 | 0.485 |
| 16 | 512 MB | 820.76 | 0.654 | 0.741 |
| 32 | 1,024 MB | 1,679.65 | 0.639 | 0.625 |

*(aggregate — egress payload `32 MiB × chunks` is already the total, the **opposite** convention to E5's
per-band `band_bytes`. Two conventions in one `timing.json`.)*

The 1-chunk point reproduces the long-standing 1.426 GB/s anchor to **0.3%** on a completely different
prompt set — the harness measures what it claims. **But the anchor holds only at its own payload**: no
larger payload exceeds 0.741 marginal, about half of it. Marginals wander in a 0.6–0.74 band with a dip at
8 chunks; **no trend, no super-linearity**.

⚠️⚠️ **RETRACTED (2026-07-31): the claim that this reverses the host-path asymmetry.** An earlier note
compared E6's rate against E5's and concluded "egress is 5.10× slower, the uplink is the fast direction".
**That comparison is invalid and the conclusion is withdrawn.** `prefill.csl:104` shows prefill's egress
is a **switch-gather along X using `fft transpose.csl`** — it carries a layout transform and a
many-PE→edge gather topology. E5's ingress is a scatter with no transform. **They are different
operations, so their rates are not comparable**, and decode's egress — which does not exist — would have
a different layout again and need not pay the same transform.

What remains true: prefill's egress is slow and gets slower with payload, and the cause is **not
separated** (transform? gather topology? wire?). It prices **prefill's** path and nothing else.

*Methodological note, recorded because it recurs:* this document elsewhere warns that E6 must not be used
to price decode offload, and then did exactly that. **A result should not be turned into a conclusion
before asking whether the two things compared are the same kind of thing** — and when a result surprises,
the experiment is a suspect before the assumption is.

## E7 · Free-decode cost vs context ✅

```
f(pos) = 623.70 µs + 28.315 ns × pos        R² = 0.99997,  n = 22
```

over mean-context 1,136 → 14,336, i.e. actual contexts to the compiled ceiling of **20,480**.
655.6 µs/token at the low end, **1,028.5 µs/token at the top — 1.57× slower**, which no constant-cost
model captures. Because a round's steady tokens span `[L_p, L_p+g]` and a linear marginal averages to
`α + β·(L_p + g/2)`, fitting round-average against mean context recovers the **marginal** coefficients —
this is `f(pos)`, not `f̄(L)`.

Three independent fits agree: S0 `627.83 + 26.45`, run-1 `623.62 + 28.34`, all-bins `623.70 + 28.315`.
The last two agree to **0.01% / 0.09%** across different runs and six prompt lengths.

## E8 · Long-context correctness ⚠️ INCONCLUSIVE — do not cite as validation

13 of 22 requests ran to the full 20,480 context, **6× beyond anything this artifact had done**. All of
them degenerate into repetition loops (distinct-4-gram → 0.00–0.15).

**But this is not a device finding.** 5 of 20 runs begin looping at context **< 3,407** — inside the range
E1 reproduced bit-identical against the HF oracle — and several begin at almost exactly `ctx ≈ L_p`, i.e.
the instant generation starts. The prompts are random word salad; a 1.7B model looping on noise is
ordinary out-of-distribution behaviour.

⇒ **No evidence of a long-context defect, and no evidence against one.** The confound is total.
⇒ **A real correctness control needs coherent long prompts.** The exact-token-count generator that made
E4–E7 possible is the wrong tool for it.

## E9 – E13 · Not yet run

See Chapter 1. E9 is the gate on E10: if `f_forced(pos)` grows with context the way `f(pos)` does, lane
A's cost is **quadratic** in `L_hist`, not linear, and the A-vs-B boundary moves sharply toward B.

---

# Chapter 3 — Design of the three-lane experiment (E9–E11)

## 3.1 The fabricated session

**Not from a dataset, by decision.** Public traces cannot serve this: Mooncake's `output_length` is
**hard-capped at 2,000 tokens** (both traces, max exactly 2,000, mean 182–343), so it structurally cannot
represent a thinking model's generation, and it is pre-reasoning-era chatbot traffic rather than an agent
session. A fabricated session is also the only way to **vary each region independently**, which is the
whole point.

Structure — a synthetic multi-turn coding-agent conversation:

```
[system prompt + tool schemas]  [turn 1 … turn k]      [new context]      [generate]
└──────────────── L_hist ───────────────────────┘      └── L_new ──┘      └─ L_gen ─┘
        KV assumed already in host DRAM                 not computed         fixed 64
```

**Requirements on the text**, each with its reason:

1. **Exact token counts per region**, verified against the launcher's own tokenizer + chat template —
   the same generator used for E4–E7, which landed all six bins exactly.
2. **Coherent, not word salad.** E8 showed noise prompts make the model loop, which destroys any
   correctness reading and distorts generation length. Regions should read as plausible agent turns
   (tool call → result → reasoning), so the same fixture can later serve E8's replacement.
3. **Non-repeating across regions**, so the fixture stays usable for prefix-reuse work and does not
   flatter any future prefix-match measurement.
4. **Region boundaries on chunk multiples** (256) where possible, so `ceil(L/256)` is unambiguous and the
   E5 measurement applies directly rather than by interpolation.
5. ⚠️ **Pin the tokenizer and chat template, and persist the rendered token IDs per region.** Exact token
   counts are only stable against a fixed tokenizer revision (`70d244cc`), a fixed chat template, and
   fixed tool-schema text; changing any of them silently moves region boundaries and invalidates
   cross-run comparison. **Analysis reads the persisted token IDs, never re-tokenizes the source text.**

## 3.2 Parameter grid

| parameter | values | why |
|---|---|---|
| `L_hist` | 0, 512, 1024, 2048, 4096, 8192 | **the main sweep** — spans E5's flat floor, its knee, and its linear region. 0 is the control (lane B degenerates to lane A) |
| `L_new` | 256, 1024, 4096 | the delta the lanes disagree about; small / medium / large relative to `L_hist` |
| `L_gen` | 64, fixed | keeps generation from confounding; E7 already prices it if needed |

Constraints, both real: `L_hist + L_new + L_gen ≤ 20,480` (decode ceiling) and, **for E11 only**,
`L_hist + L_new ≤ 8,192` (prefill `MAX_INPUT_LEN`). The grid is trimmed to satisfy both.

## 3.3 The ingress payload, stated in bytes

Lane B's cost must be predicted **from bytes, not from token labels**. The exact formula, derived from
and exact on all six E5 bins:

```
band_bytes = 8 MiB × ceil(L/256) + 1 MiB          (1 MiB constant tracks KV_META_LEN = 4)
total      = 4 × band_bytes = 32 MiB × ceil(L/256) + 4 MiB
```

`ceil` matters: a partial chunk is loaded as a **whole** chunk, so `L_hist = 700` costs the same as
`L_hist = 768`. The grid in §3.2 is deliberately chosen so **every `L_hist` lands on an exact chunk
multiple that E5 already measured** — so lane B's reload cost is **measured, not modelled**:

| `L_hist` | chunks | `band_bytes` | ingress | source |
|---|---|---|---|---|
| 512 | 2 | 17,825,792 | **46.236 ms** | E5, measured |
| 1,024 | 4 | 34,603,008 | **56.141 ms** | E5, measured |
| 2,048 | 8 | 68,157,440 | **85.684 ms** | E5, measured |
| 4,096 | 16 | 135,266,304 | **169.891 ms** | E5, measured |
| 8,192 | 32 | 269,484,032 | **338.266 ms** | E5, measured |

⚠️ This assumes the KV injected for `L_hist` uses the **same per-round path** E5 timed. If lane B's
injection differs in any way, these are predictions rather than measurements and must be re-timed —
`kv_ingress_span_us` is reported per round, so E10 verifies this rather than assuming it.

## 3.4 Pre-recorded predictions

**Written before any of E9–E11 runs.** These are what the experiment is trying to falsify.

⚠️ **These are a fragile prior, not a robust expectation.** The whole E10 prediction rests on an
intercept **back-solved from E3's single short-context point**. That is a hypothesis worth writing down
so it can be scored — it is *not* strong evidence, and E5 already demonstrated in this project that a
confidently-fitted extrapolation can be 27% wrong. **E9 runs first and replaces this prior with a
measured fit before E10's crossing band is treated as meaningful.**

**E9 — `f_forced(pos)`.** Prediction: forced tokens carry the **same context slope as free tokens**,
because both scan the same growing KV cache; only the fixed per-token term differs.

```
predicted:  f_forced(pos) ≈ 57 µs + 28.3 ns × pos
```

**Falsifier:** if the fitted slope is < 10 **ns**/token, forced tokens are context-independent and E3's
constant is safe to multiply; if it is ≥ 20 **ns**/token, lane A is **quadratic** in `L_hist` and E3's
88.35 µs must never be multiplied by a large `F`.

**E10 — the A/B crossing, under two envelopes.** Because E9 has not run, both plausible forced-token
models are carried, and E10 is scored against whichever E9 selects:

| `L_hist` | lane A, **E3-constant** envelope (88.35 µs flat) | lane A, **E9-slope** envelope (quadratic) | lane B (measured) |
|---|---|---|---|
| 512 | 45.2 ms | ~36 ms | **46.24 ms** |
| 1,024 | 90.5 ms | ~75 ms | **56.14 ms** |
| 2,048 | 180.9 ms | ~176 ms | **85.68 ms** |
| 4,096 | 361.9 ms | ~471 ms | **169.89 ms** |
| 8,192 | 723.8 ms | ~1,420 ms | **338.27 ms** |

⇒ crossing predicted at `L_hist` ≈ **520 tokens** (constant envelope) or ≈ **700–900** (quadratic
envelope). **Falsifier:** a crossing outside 400–1,500 under *both* envelopes kills the model. The
envelopes separate most strongly at `L_hist = 8192` (724 vs 1,420 ms), so **that point discriminates
which forced-token model is right** even independently of E9.

⚠️ **The `L_new` cancellation is a HYPOTHESIS, not an identity.** Both lanes are charged `Σ f_forced`
over `L_new`, and it is tempting to say this cancels. **It only cancels if lane B's forced decode starts
from a state equivalent to lane A's** — same KV layout, no extra warm-up, queue drain, metadata pass or
first-token penalty left behind by the ingress. Treating that as automatic would repeat exactly the E6
error. **E10 therefore measures the two segments separately** rather than comparing totals:

```
lane B:  total  −  kv_ingress_span_us  =  post-ingress forced-decode segment
lane A:  total                          =  full-rebuild forced-decode segment
```

and reports **both** "reload overhead" and "post-ingress forced-token cost". If the per-token cost of
`L_new` differs between lanes, that difference **is the finding**, not noise to be cancelled away.

**E11 — the full re-prefill baseline.** Prefill's amortised per-token cost was ~103–156 µs across E4–E7's
bins, i.e. **not obviously cheaper than a forced token**. Prediction: it **loses to lane B at every
`L_hist` ≥ 1,024**, paying a prefill floor *and* a full-payload ingress.

⚠️ **Naming and inference limits.** This is a **substitute**, not an upper bound in the strict sense: it
replaces delta-prefill-with-resident-history by full-prefill-from-scratch, which is a different
computation with a different attention shape and different KV movement. Therefore:
**if it loses, true lane C may still win** (it does strictly less prefill work); **if it wins, true lane C
is worth building** (E12). Only the second direction is conclusive.

## 3.5 What each experiment plots

| ID | figure | x | y | series | what a reader should see |
|---|---|---|---|---|---|
| E9 | forced-token cost | force-decode position | µs/forced token | one line, plus E7's free-token line for scale | whether the two lines are parallel |
| E10 | **the resume-latency boundary** | `L_hist` | resume latency (ms), log y | lane A, lane B; one panel per `L_new` | two lines crossing once, B pulling away |
| E10b | decomposition | `L_hist` | stacked ms | ingress / forced-decode / fixed | which term owns the cost in each regime |
| E11 | full re-prefill baseline | `L_hist + L_new` | resume latency (ms) | A, B, C0 | whether C0 is ever below the other two |

## 3.6 Build status and honesty about scope

| lane | measurable today? | what is missing |
|---|---|---|
| A | ✅ | nothing — E3's mechanism with large `F` |
| B | ✅ **resume only** | the *eviction* half (decode→host) is **E13, unbuilt**. E10 assumes DRAM already holds `L_hist`, which the scenario justifies but which hides a recurring cost |
| C | ❌ | prefill has **egress only** — no KV ingestion (`src/prefill/` has `kv_egress_colmux.csl` and no counterpart). E11 measures a bound, not the lane |

**E10's result will therefore be a statement about resume latency in a session whose history is already
persisted — not a full offload-vs-recompute verdict.** Stating this in the figure caption is part of the
deliverable.

### Known confound: history provenance

`L_hist` is **assumed resident** — fabricated and injected, never actually produced by an earlier decode
turn. This does not affect the resume-latency measurement (the bytes and the path are the same), but it
means E10 cannot see whether **decode-produced** KV and **host-resident/reloaded** KV stay equivalent over
a long history. That is precisely the question a real eviction/resume cycle would face.

⇒ Recorded as a limitation now, and testable later with a small equivalence control: build a short
history by force-decode, resume from it, and compare against the fabricated-resident path. That control
needs E13 (or some other way to read decode-side KV back out), so it is **not** available in this round —
which is itself an argument for E13 beyond raw transport cost.

---

## Change log

- **2026-07-31** — register created. E6's "asymmetry reversed / 5.10×" claim **retracted** (prefill egress
  carries a transpose + gather; not comparable to decode ingress). A7's falsification **withdrawn**
  (Mooncake `output_length` capped at 2,000). Scenario fixed to the three-lane resume race; E9–E13 defined.
