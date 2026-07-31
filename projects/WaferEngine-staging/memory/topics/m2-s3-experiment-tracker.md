---
summary: M2-S3 experiment tracker — offload vs recompute; design, assumptions register, discovery chain, dataset choice, scenario values.
tags: [waferengine-staging, kv-cache, m2, experiment-tracking, measurement]
---

# M2-S3 Experiment Tracker — offload vs recompute

> **Mirror of the ContextBase living tracker**
> https://context.ed-aisys.com/doc/m2-s3-experiment-tracker-offload-vs-recompute-design-assumptions-discovery-chain-smzbH7hS1u
> Subtask *status* lives in `milestones/M2-tiering-cost-model.md` (source of truth); this owns design,
> assumptions and the discovery chain. Related: [[agentic-kv-trace-datasets]],
> [[m2-s1-measurement-lenses]], [[m2-s2-force-decode-port]], [[prefill-decode-transfer-bandwidth]].

> **Living experiment tracker for M2-S3 — the offload-vs-recompute boundary.** Owns the experimental
> *design*, the *assumptions*, and the *discovery chain*. It does **not** own subtask status: the
> checkboxes live in `milestones/M2-tiering-cost-model.md`, which stays the single source of truth for
> plan and state. Written to be read top-down in a meeting.
>
> **Status: no S3 experiment has run yet.** Everything below is design and prediction. Predictions are
> recorded *before* the runs on purpose — see § Discipline.

## 1. The question, in one paragraph

A request's KV cache must be evicted from the decode PEs. Do we **offload it to host DRAM and reload it
later**, or **discard it and rebuild it** (force-decode in place, or regenerate in prefill)? M2's job is
to turn that into a falsifiable boundary with a measurement behind it. As of today **we cannot answer
it**, because the transport half of the comparison has no valid number.

## 2. Where we actually are

| | state |
|---|---|
| **S0** baseline reproduced bit-identical on real WSE-3 | ✅ 2026-07-28, `n=2` |
| **S1** measurement lenses fixed; H2D uplink "measured" | ✅ 2026-07-30 — ⚠️ **the number it produced was later falsified as a rate** |
| **S2** force-decode ported + device-verified | ✅ 2026-07-30, `dd0d950`. `F=64`, **10,067 tokens bit-identical** across 8 requests |
| **S30** fabricated request set + payload sweep | ⬜ **NEXT — and the gate on everything below** |
| **S2b / S3a / S3b / S3c / S4 / S5** | ⬜ blocked or not started |

**The blocking fact:** the only two transport numbers we have (`0.7726 GB/s` H2D, `1.426 GB/s` D2H) are
**not usable** — one is falsified, the other is untested and structurally suspect. Every lane cost that
involves moving KV is therefore unsupported.

## 3. The discovery chain — how we got here

Each step falsified the previous step's headline. This is the context a meeting needs.

1. **S0 (07-28).** pdSeparate baseline reproduced bit-identical, `n=2`. Also: decode cost is **linear in
   context**, `627.83 µs + 26.45 ns × ctx` (R² = 0.998) — so the 654.955 µs anchor is a *mean over one
   workload's generation-length mix*, not a constant.
2. **S1 (07-30).** Added a device-TSC pair on the KV ingress adaptor, because **no host-side timer on
   this SDK can see the H2D wire** (`task_wait` on a `nonblock` send returns 51.15 GB/s = 4.5× the
   physical ceiling). Reported **0.7726 GB/s aggregate**, "1.85× slower than the downlink". This
   re-priced the reload lane 753 → 1390 ms and was, at the time, the headline result.
3. **S2 (07-30).** Force-decode ported and verified. **Forced token = 13.50% of a free one (7.41×),
   88.35 µs** — the first same-line measurement of a ratio that had only been predicted (11.7–12.0% on a
   mock-weight standalone line). *Incidentally*, S2's Step-0b widened the KV-meta tile, which was the
   **first controlled payload change ever made on this path** — and it broke S1's number.
4. **The falsification (07-30).** Payload **+5.882%**, device-TSC span **+0.0085%**. The measurement
   **contradicts its own rate by 721×**: at 0.1931 GB/s the extra 524,288 B should have cost 2.715 ms;
   it cost 3.764 µs.
5. **The diagnosis (07-30).** The marker is **correctly placed** — tic after the first wavelet lands,
   toc after the last is accepted, no barrier. **The defect is the divisor.** The path is **per-step
   bound, not wire-bound**: ~2,356,992 blocking fabric ops per round at ~16.6 cycles each, moving
   **0.95 wavelets per op**, i.e. **17.6× off the 1-wavelet/cycle fabric limit**. It only *looked* like a
   bandwidth because at `KV_META_LEN = 2` bytes and steps were **coincidentally proportional**.

**Two structural findings fall out, and they are the durable ones:**

- **Both KV transport paths on this machine are per-step bound.** The on-chip prefill→decode relay pays
  a fixed **~4.54 µs per store-and-forward step carrying 16 B** (wire idle 99.91%); the host ingress
  pays **~16.6 cycles per op at 0.95 wavelets/op**. Two unrelated paths, same disease. ⇒ **on this
  machine the lever is step count, not bandwidth.**
- **Cross-run reproducibility is not validity.** The falsified figure reproduced to the *microsecond*
  across five runs and three compiles — mean, min **and** max identical to three decimals. That
  determinism was the tell, not the reassurance.

## 4. Assumptions register

Everything the S3 design rests on, with what breaks if it is wrong.

| # | assumption | status | if wrong |
|---|---|---|---|
| A1 | `request_config/` is **not** in the artifact fingerprint ⇒ new prompts need no rebuild | ✅ **verified** in `launch_device.py:88-100` | the sweep costs a 40-min rebuild per point instead of being serve-only |
| A2 | `L ≤ 8192` fits the compiled `MAX_INPUT_LEN` ⇒ no config change | ✅ verified (config) | same |
| A3 | `kv_ingress_device` has **no per-round array** — only `mean/min/max/spread_pct` | ✅ verified in `timing.json` | a mixed-payload run could give a slope directly, and the design gets simpler |
| A4 | Ingress is **per-step bound**; payload rides free inside existing ops | ⬜ **this is what S30 tests** | if per-byte, `0.7726 GB/s` was roughly right and "recompute wins as-built" is restored |
| A5 | Egress (`1.426 GB/s`) has the same defect | ⬜ **untested** — same single-payload-point problem, same store-and-forward colmux shape ⇒ **structurally suspect, not falsified** | if egress *is* a real rate, the D2H half of the round trip survives and only H2D needs re-deriving |
| A6 | In pdSeparate the host retains a copy of the **prompt** KV during a request, so the `L_p` half of a reload pays H2D only | ⚠️ **inferred from the npz flow, never confirmed in code** | the `L_p` half also pays D2H; the round-trip threshold applies to the whole payload |
| A7 | `L_g ≫ L_p` in the scenarios that matter | ⚠️ **DERIVED FROM A VALIDATION FIXTURE — needs re-grounding.** The 98.1% figure came from `mtbench8`, whose prompts are **21–36 tokens** because it is a bit-identity regression fixture, **not a serving workload**. Real serving prompts run to thousands of tokens | **this is load-bearing**: it is the stated reason S3b (decode egress) was promoted from *conditional* to *prerequisite*. If `L_p` dominates in realistic workloads, the prompt half has a free host copy and S3b's promotion must be re-argued |
| A8 | Force-decode's rebuilt KV reaches a functionally equivalent end state | ⚠️ partial — S2 verified **sampled tokens** match at `F=64`; KV bit-identity is **not** available by construction (prompt KV came from *prefill*, force-decode rebuilds it in *decode*) | the A-vs-B race is not comparing one end state and the gate must change |
| A9 | Prompts can be generated to hit exact tokenized-length bins | ⬜ to verify — `PREFILL_LENS` derives from tokenizing the prompt **text**, not from a label | bins must be found by search rather than construction |

## 5. Dataset selection, and why synthetic

**Decision: this round uses a synthetic, fully controlled request set. Real data is for S5.**

Reasons, in order of weight:

1. **The sweep needs exact token bins.** Because `PREFILL_LENS` comes from tokenizing the text (A9), a
   calibration needs prompts that land *on* 256/512/1024/2048/4096/8192. Real text does not.
   **Control beats realism for a calibration.**
2. **The measurements are content-blind.** Transport sees bytes; `f(pos)` sees context length. Neither
   depends on what the tokens mean.
3. **Realism is S5's job.** Witness workloads are where turn structure and prefix overlap matter.

⚠️ **A framing error worth recording: `mtbench8` is a validation fixture, not a serving workload.** Its
21–36-token prompts exist to make bit-identity regression cheap. Two things were mistakenly read off it
as if they characterised serving: the `L_g ≫ L_p` ratio (A7), and the **8.5× chunk-padding waste**,
which only occurs at `L < 256` and is likewise a fixture artifact. **Real serving prompts are far
longer**, and the design below reflects that.

**Filler must be non-repeating** (random token ids, or real text sliced from a long-document corpus) so
the same request set stays usable for prefix-reuse work later. Cost is the same; repeated filler would
bias any future prefix-match measurement optimistically.

**For S5, a researched shortlist already exists** — see the agent-memory topic
`topics/agentic-kv-trace-datasets.md` (2026-07-05), which I had missed when first proposing datasets and
which supersedes the ad-hoc suggestions:

| source | why | state |
|---|---|---|
| **TraceLab** — *Characterizing Coding Agent Workloads for LLM Serving* | **closest fit.** ~4,300 coding-agent sessions, ~350K LLM steps, ~430K tool calls, from real **Claude Code + Codex** usage, with **timing**; analyses prefix-cache hit rate and tool-call overhead directly. Shape: long contexts, short outputs, long autonomous loops. CC-BY-4.0 | shortlisted, **not yet cloned** |
| **Mooncake** request traces (Kimi/Moonshot, FAST'25) | `hash_ids` per 512-token KV block make **prefix sharing exactly computable with no inference**. Published ratios: conversation **~40%**, **tool&agent ~59%**. Use the tool&agent trace | schema + access path recorded; **not cloned** |
| **CacheTTL / Continuum** (arXiv 2511.02230) | does *literally this tradeoff* — KV time-to-live across the tool-call gap; read for methodology framing | reference |

⚠️ **Correction to an earlier claim in `milestones/M2-tiering-cost-model.md` S5:** I wrote that the
Mooncake grounding "may not be actionable — no such trace exists in this repo, and no download path or
extraction command has ever been recorded." **The second half is wrong.** The trace is not checked in,
but the access path (`github.com/kvcache-ai/Mooncake`, `FAST25-release/traces/`), the JSONL schema, and
the `hash_ids` semantics **are** recorded in agent-memory. S5's grounding is a `git clone`, not a
research problem.

**Also on this machine already**, under `/data/huggingface/datasets/`: **SWE-bench** (code-agent prompts
often >10k tokens), **LongBench-v2** (long-document), **StableToolBench** (tool-call). Useful as filler
material for realistic long prompts; not substitutes for a timed agentic trace.

## 6. The capacity envelope (code-derived, no compile)

| limit | value | source |
|---|---|---|
| max **prompt** | **8,192** = `MAX_INPUT_LEN` | the prefill artifact's own `MAX_SEQ_LEN` |
| max **total context** (prompt + generated), compiled | **20,480** = `MAX_OUTPUT_LEN` ⚠️ **not** `MAX_INPUT_LEN + MAX_OUTPUT_LEN` | orchestrator maps `decode ← MAX_OUTPUT_LEN` |
| hard wall with a decode-only rebuild | **32,512** = 127 × 256 | **three independent walls land here**, coinciding only because `P_BLOCK_SIZE = 256`: an **i8 memory-DSD stride** (likely a loud compile error), **i16 `n_steps`** and **i16 absolute position** (both **silent wraps**) |
| per-PE KV cache | **5,120 B** for the full 20,480 context = **64 B per 256 tok** (total context-scaled footprint **84 B**, incl. score + ingress buffer) | aggregated: **131,072 B/token = 128 KiB = exactly `8/7 · B_tok`** |

**SRAM does not bind decode** — context-scaled PEs have ~25 KB headroom; the tight PEs (HT_head
`W_E_tile`, HT_tail `lm_head_tile`, 19,008 B each) are vocab-sized and context-independent.

⚠️ **Never exercised past ~3,407 tokens** — the longest context any `mtbench8` round reached. A sweep to
16,384 runs **~5× beyond anything this artifact has done**, and decode's RoPE is an f32 recurrence
advanced once per step with **no assert watching drift**. Long-context points therefore need a
**correctness control**, not only timing.

## 7. The experiment ladder

### S30 · Run 1 — the discriminator (one run, no rebuild)

**Question:** does ingress time depend on bytes *at all*? Not "what is the rate" — just the direction.

Because `kv_ingress_device` reports only extremes over rounds (A3), a single run whose 8 rounds span
**1 → 32 chunks** answers it from one field:

| model | predicted `spread_pct` |
|---|---|
| **per-step** (current analysis) | **~0.005%** — today's value, i.e. payload-independent |
| **per-byte** (retired reading) | **~3,100%** (max/min → 32) |

Generation fixed **short (64 tokens)** so the decode budget cannot confound and the run stays fast.
*Budget: 1 run, 3 attempts.* **If per-byte → per-bin runs follow, to fit the slope.**

**Egress rides along free:** the same run gives `per_req_kv_egress_ms` against `ceil(L/256)`, which
settles A5.

### Prompt set (one `prompts.json`, several `request.json` variants)

| # | `L_p` | `ceil(L/256)` | role |
|---|---|---|---|
| 0 | 256 | 1 | sweep floor |
| 1 | 512 | 2 | sweep |
| 2 | 1,024 | 4 | sweep |
| 3 | 2,048 | 8 | sweep |
| 4 | 4,096 | 16 | sweep |
| 5 | 8,192 | 32 | sweep ceiling = `MAX_INPUT_LEN` |
| 6 | 256 | 1 | scenario control |
| 7 | 4,096 | 16 | scenario control |

### Scenario values for the A-vs-B race (S3c) — sized for real serving, not the fixture

| scenario | `L_p` | `L_g` at eviction | total | `L_p` share | shape |
|---|---|---|---|---|---|
| **A · long session preempted** | 2,048 | 8,192 | 10,240 | 20% | generation-dominant — the `L_g` half must pay D2H |
| **B · tool-call interruption** | 4,096 | 2,048 | 6,144 | 67% | long tool schema + moderate generation |
| **C · long-document QA** | 8,192 | 1,024 | 9,216 | **89%** | prompt-dominant — the prompt half has a free host copy **if A6 holds** |
| **D · control** | 4,096 | 4,096 | 8,192 | 50% | even split |

**A and C are the informative pair:** `L_p` share swings 20% → 89%, which puts **A6 and A7 directly
under test** rather than leaving them as assumptions. All totals ≤ 20,480 ✓.

### Then, in order

**S2b** force-decode vs prefill (pure compute, zero transport — may drop the "regenerate in prefill"
lane unconditionally) → **S3a** the `f(pos)` curve to 16,384 with a long-context correctness control →
**S3b** decode→host egress (⚠️ its promotion depends on A7, which needs re-grounding first) → **S3c**
the race → **S4** the boundary.

## 8. Discipline — the rules this round runs under

Each was bought with a failure earlier in the project.

- **A transport number is not trustworthy until the payload has been varied and the time has moved
  proportionally.** Three numbers have now died on this path for want of that test: an *enqueue* read as
  wire time (575 GB/s), `task_wait` on a `nonblock` send (51.15 GB/s), and the ingress average
  (self-inconsistent by 721×).
- **Predictions outside the fit range go in writing before the run.** Validating a model only where it
  was fit validates nothing.
- **Device TSC only for anything on a wire** — no host-side timer on this SDK can see it.
- **Payloads are code-derived, never assumed.**
- **Budget attempts, not successes** — ~half of CS-3 runs die on cluster infrastructure (2 of 5 in S0).
  Every number carries its `n`, and `n = 1` is stated as such.
- **A checker whose input can legitimately be empty must refuse, not pass.**

## 9. Open questions

1. **A7 re-grounding** — is `L_g ≫ L_p` true for realistic serving, or was it a fixture artifact? This
   decides whether S3b stays a prerequisite. **Highest priority; the scenario table above is designed to
   answer it.**
2. **A6** — does the host actually retain the prompt KV copy? Ten minutes of code reading; currently
   inferred.
3. **A5** — is egress a real rate? Answered free by Run 1.
4. Where the 46.146 ms actually goes, if not on the wire — the per-step model accounts for it
   arithmetically (2.36 M × 16.6 cyc) but the 16.64 cycles/step figure is a **residual**, not an
   independent measurement.
5. **Parked (Le, 2026-07-30):** the per-step optimisation itself — async ping-pong relay, then
   hardware-routed scatter. **Do not act before the measurement lands**: if ingress goes 46 ms → ~3–5 ms
   the reload lane gets ~10× cheaper and the boundary moves a long way, so the measurement must define
   the target first. An independent review corrected the ladder — **double-buffering alone buys
   nothing** (program order + blocking ops are the serialiser), the ~500× step collapse is an unproven
   design target, and 17.6× is a **fabric-only lower bound**, not a ceiling.

## 10. Run log

*(Append one row per device run: date, run id, config, request set, `n`, what it tested, the number, and
whether the pre-recorded prediction held.)*

| date | run | config / request set | `n` | tested | result | prediction held? |
|---|---|---|---|---|---|---|
| 2026-07-31 | `s30_run1`, `rc=0` first attempt, ~19 min | `serve_2x4_8k20k_s2` / `request_config/s30_sweep` | 1 | is ingress payload-dependent at all? | **`spread_pct = 243.834%`** — ingress is **AFFINE** | ❌ **both predictions wrong** |

## Run 1 result (2026-07-31) — the boundary is decided by PROVENANCE

**Both pre-recorded predictions were wrong**, and that is the finding. per-step predicted
`spread_pct ≈ 0.005%`; per-byte predicted `≈ 2,756%`. **Measured 243.834%.** The truth is a third thing
neither hypothesis named — **affine**:

```
t_ingress(band) = 35.55 ms + bytes / 0.8902 GB/s     (per stream)
                              marginal aggregate = 3.561 GB/s
```

- At the 1-chunk payload **every previous run used**, the fixed cost is **77% of the span** — which is
  exactly why the ratio looked like a bandwidth and behaved like a constant.
- **The marginal H2D rate is 4.61× the retired 0.7726 GB/s "average".**
- **The lever provably moved**: `band_bytes` matched the code-derived prediction **to the byte**
  (84,934,656 mean); the device trace confirms prompts at `[256,512,1024,2048,4096,8192,256,4096]`.

⚠️⚠️ **RETRACTED 2026-07-31 (Le).** `per_req_kv_egress_ms` times **prefill→host** egress — the *prefill*
kernel's own path in the normal pdSeparate flow. **It is not the cost of offloading a decode-resident
KV**, which does not exist yet (S3b, unbuilt). Same substitution error as S1's 1.85×. **The
"decode-produced ⇒ recompute wins" column, the reversed asymmetry, and the 0.632 GB/s marginal are all
withdrawn.** The **ingress/reload** result stands — it was measured on the reload path itself — so the
**prefill-produced** lane survives. Offload cost for a decode-produced prefix: **no measurement exists.**

**~~Egress goes the other way, and the asymmetry has REVERSED.~~** `per_req_kv_egress_ms` is the mean over
rounds (`launch_prefill.py:1658`): **501.372 ms at a 10-chunk mean ⇒ 0.669 GB/s**, vs **1.428 GB/s** on
the old all-1-chunk workload — **2.13× worse per byte at 10× payload**. Two aggregate points fit with a
**negative intercept (−29.6 ms) ⇒ SUPER-linear**, marginal ≈ **0.632 GB/s**. The retired claim was
"uplink 1.85× slower than downlink"; **marginally egress is 5.6× slower than ingress**.

| `L` | force-decode | reload (prefill-produced, H2D only) | + egress (decode-produced) |
|---|---|---|---|
| 1,024 | 76 ms | **73 ms** offload | 286 ms recompute |
| 4,096 | 323 ms | **186 ms** offload | 1,036 ms recompute |
| 8,192 | 698 ms | **337 ms** offload 2.1× | 2,036 ms recompute |
| 16,384 | 1,601 ms | **639 ms** offload 2.5× | 4,037 ms recompute |

⇒ **prefill-produced KV → OFFLOAD wins above `L ≈ 953`. decode-produced KV → RECOMPUTE still wins.**
So **A6** (host retains the prompt KV copy?) and **A7** (`L_g` vs `L_p` in real serving) are no longer
background assumptions — **they decide the answer**.

**Also:** prefill at `L=8192` measured **1,280 ms** vs the **1,001 ms** anchor — **28% optimistic**.

**Caveats:** `n = 1`. The ingress fit is two points; the unused third constraint (the mean) is **9.3%
off**, i.e. slightly sub-affine, so the fit **over-predicts the middle** — a proper fit needs per-bin
runs. The egress conclusion rests on **two aggregate points from different runs/configs** — suggestive,
not settled.



## A7 RE-GROUNDED FROM REAL TRACES — 2026-07-31, and it is FALSIFIED

Cloned `github.com/kvcache-ai/Mooncake` (`FAST25-release/traces/`) and computed the length distribution
directly. **Zero wafer time.**

| trace | n requests | `L_p` median | `L_g` median | **`L_p` share of all tokens** | requests with `L_p > L_g` |
|---|---|---|---|---|---|
| `conversation_trace` | 12,031 | **6,909** | 350 | **97.2%** | **99.9%** |
| `toolagent_trace` | 23,608 | **6,346** | 30 | **97.9%** | **99.9%** |

**A7 said `L_g ≫ L_p`. Real serving is the exact opposite: `L_p` is ~98% of all tokens, in both traces,
across 35,639 requests.** The 98.1% *`L_g`* share that A7 rested on came from `mtbench8`, whose 21–36
token prompts exist only to make bit-identity regression cheap. Le flagged this as a fixture artifact
before the data confirmed it.

**Two consequences, recorded as facts — the plan call is Le's:**

1. **The stated reason for promoting S3b (decode→host egress) from *conditional* to *prerequisite* is
   gone.** That reason was "essentially all long-lived KV is decode-produced, so without egress the
   offload lane covers ~0% of real scenarios." The traces say the opposite.
2. **Combined with A6 (confirmed today: the host *does* retain the prompt KV — `inj_{i}.npz` is written
   with `np.savez` and never deleted, `launch.py:419-431`), the prefill-produced lane — the one that
   survived the egress retraction and is actually measured — covers ~98% of real tokens.**

⚠️ **Caveats.** Mooncake is a **GPU-serving trace from Kimi/Moonshot** — different model, different
engine. Length distribution is a workload property rather than an engine property so it should transfer,
but it is not our model and not our workload. Also unverified: whether `input_length` already includes
prefix retained from earlier turns.

⚠️ **Separately relevant to our capacity envelope:** median input is **6,909 / 6,346**, *below* our
compiled `MAX_INPUT_LEN = 8192` — but **p90 is 27,367 / 16,810, well above it**, and max is 126,195.
So a real workload would exceed our compiled prompt cap on **roughly 10–25% of requests**.


## Two curves fitted from s30_run1 data — 2026-07-31, zero extra wafer time

Both from `evidence/s30_run1/` (already collected). Setting as in § Run 2. `n = 1`.

### (a) DECODE cost vs context — the anchor is CONFIRMED, and extended 7× beyond its fit range

```
s30_run1 fit : 623.62 us + 28.34 ns x ctx      R^2 = 1.0000   (contexts 1,290 – 14,344)
doc anchor   : 627.83 us + 26.45 ns x ctx      R^2 = 0.998    (contexts  ~600 –  2,000, mtbench8)
```

Intercept agrees to **0.7%**, slope to **7%**. **The anchor was fit on contexts 600–2,000 and this run
independently reproduces it out to 14,344 — ~7× beyond the fit range — with R² = 1.0000.**

⇒ **`f̄(L)`, the rebuild side of the boundary, is validated far past where it was previously supported.**
This is most of what M2-S3a set out to establish, obtained with no additional wafer time.
⚠️ It validates **timing linearity only**. The separate RoPE-drift concern is a *correctness* question
and is untouched by this — a long-context correctness control is still required.

### (b) PREFILL cost is NOT affine — per-token cost is U-shaped, minimum near L = 2,048

| `L_p` | chunks | span | µs/token |
|---|---|---|---|
| 256 | 1 | 56.9 ms | 222.3 |
| 512 | 2 | 74.5 ms | 145.4 |
| 1,024 | 4 | 114.0 ms | 111.3 |
| **2,048** | 8 | 210.5 ms | **102.8  ← minimum** |
| 4,096 | 16 | 473.6 ms | 115.6 |
| 8,192 | 32 | 1,280.4 ms | 156.3 |

An affine fit gives a **negative intercept (−45 ms) and only R² = 0.977** ⇒ **affine is the wrong model
for prefill.** The fixed floor dominates at small `L`; efficiency peaks around 2,048; then the quadratic
attention term takes over and per-token cost climbs again.

**The doc anchor "122 µs/token amortized @ L=8192 ⇒ 1,001 ms" measures 1,280 ms here — 28% higher.**
⚠️ The anchor came from **standalone prefill**, a different config, so part of that gap may be
configuration rather than error. Recorded as a discrepancy to resolve, not as a correction.

**Both results are facts from existing data. No plan conclusion drawn — that is Le's call.**


## Run 2 INTERIM — 3 of 6 bins (2026-07-31). The affine model is in doubt.

Setting as in § 11. Each bin: all rounds at ONE payload, so `spread_pct` is a **noise estimate**.

| `L_p` | chunks | `band_bytes` | `mean_span_us` | `spread_pct` | rounds | lever verified |
|---|---|---|---|---|---|---|
| 256 | 1 | 9,437,184 | 46,149.6 | 0.003% | 4 | ✅ all 256 |
| 512 | 2 | 17,825,792 | 46,236.5 | 0.003% | 4 | ✅ all 512 |
| 1,024 | 4 | 34,603,008 | 56,141.0 | 0.002% | 4 | ✅ all 1,024 |

`band_bytes` matched the code-derived value exactly in every bin. **Noise floor is 0.002–0.003%**, so the
gaps below are signal, not scatter.

**The marginal cost per byte is NOT constant — it rises steeply with payload:**

| segment | added bytes | added time | marginal |
|---|---|---|---|
| 1 → 2 chunks | +8.00 MB | **+0.087 ms** | 10.9 µs/MB = **96.5 GB/s** ⇐ impossible as a rate ⇒ fixed cost still dominates here |
| 2 → 4 chunks | +16.00 MB | **+9.905 ms** | 619 µs/MB = **1.694 GB/s** |
| 1 → 32 chunks (run-1, two-point) | +248 MB | +292.1 ms | 1,178 µs/MB = **0.890 GB/s** |

⇒ **the shape is convex/super-linear, not affine.** Run 1's two-point fit assumed a constant slope; the
9.3% mid-range error it showed was the first sign, and this is the mechanism behind it. An affine fit on
these three points gives only **R² = 0.897**, which is poor for 3 points.

⚠️ **NOT CONCLUDING. 3 of 6 bins.** The remaining bins — 8, 16 and 32 chunks — are precisely the ones
that set the top-end shape and therefore decide this. The marginal rate that the cost model needs is the
one at the payload sizes that matter, and it is **not yet measured**.

⚠️ **Self-correction:** an earlier line in this session quoted run-1's overall slope as "1.123 µs/MB".
That was a unit slip (s/B → µs/MB, off by 1000×). The correct figure is **1,178 µs/MB**; the GB/s
figures were unaffected.

**Infra note:** `s30_bin0512` attempt 1 died on **EPCC ingress gRPC 502** — the known signature, not a
config fault. Attempt 2 succeeded. Confirming this mattered: a config fault would have failed every
remaining bin identically.

## Last updated

2026-07-31
