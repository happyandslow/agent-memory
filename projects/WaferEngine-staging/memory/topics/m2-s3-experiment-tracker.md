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
> **Status (2026-07-31): S30 COMPLETE — Run 1 ✅, Run 2 ✅ all 6 bins.** §§ 1–11 are the design and the
> pre-run predictions, left un-rewritten on purpose (see § Discipline) — *including the ones that turned
> out wrong*. **The results are in the sections after § 11; they supersede §§ 1–11 wherever they
> disagree.** Headline: the H2D reload path is a **hockey stick** — flat ~46 ms floor below ~2 chunks,
> then a line through the origin at **0.797 GB/s per band = 3.186 GB/s aggregate** (R² = 1.000000). At
> `L = 8192` a reload is **338.3 ms measured**, beating force-decode (723.8 ms) by **2.14×**. The
> **offload** half is still unbuilt and unjudged.

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
| **S30** fabricated request set + payload sweep | ✅ **COMPLETE 2026-07-31** — Run 1 (A4 falsified: ingress IS payload-dependent) + Run 2 all 6 bins (hockey stick, marginal saturates at 0.797 GB/s/band) |
| **S2b / S3a / S3b / S3c / S4 / S5** | ⬜ blocked or not started |

⚠️ *(This paragraph was the pre-S30 framing and is now **out of date**; kept because § 3's discovery
chain refers to it.)* **The blocking fact:** the only two transport numbers we have (`0.7726 GB/s` H2D,
`1.426 GB/s` D2H) are **not usable** — one is falsified, the other is untested and structurally suspect.
Every lane cost that involves moving KV is therefore unsupported.

**As of 2026-07-31 this is resolved for the reload direction.** S30 measured both host paths against a
six-point payload sweep. The **reload (H2D) lane now has a validated model** — hockey stick, marginal
0.797 GB/s per band = 3.186 GB/s aggregate, `L = 8192` reload = 338.3 ms measured. The **offload (D2H)
lane for decode-resident KV remains unsupported**, because that kernel does not exist (S3b). So one lane
cost is now grounded and one is still blocked — not "every lane".

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
| A4 | Ingress is **per-step bound**; payload rides free inside existing ops | ❌ **FALSIFIED by S30** — above ~2 chunks the cost is purely per-byte (R² = 1.000000, zero intercept); the per-step floor exists but caps out at ~46 ms | if per-byte, `0.7726 GB/s` was roughly right and "recompute wins as-built" is restored |
| A5 | Egress (`1.426 GB/s`) has the same defect | ⚠️ **PARTLY — settled by S30**: egress *is* broadly a real rate (~0.63 GB/s aggregate marginal, no super-linearity), but the 1.426 anchor is an outlier valid only at 1 chunk. Previously — same single-payload-point problem, same store-and-forward colmux shape ⇒ **structurally suspect, not falsified** | if egress *is* a real rate, the D2H half of the round trip survives and only H2D needs re-deriving |
| A6 | In pdSeparate the host retains a copy of the **prompt** KV during a request, so the `L_p` half of a reload pays H2D only | ✅ **VERIFIED in code** — `launch.py:405-431` writes `inj_{i}.npz` and never deletes it | the `L_p` half also pays D2H; the round-trip threshold applies to the whole payload |
| A7 | `L_g ≫ L_p` in the scenarios that matter | ⚠️ **DERIVED FROM A VALIDATION FIXTURE — needs re-grounding.** The 98.1% figure came from `mtbench8`, whose prompts are **21–36 tokens** because it is a bit-identity regression fixture, **not a serving workload**. Real serving prompts run to thousands of tokens | **this is load-bearing**: it is the stated reason S3b (decode egress) was promoted from *conditional* to *prerequisite*. If `L_p` dominates in realistic workloads, the prompt half has a free host copy and S3b's promotion must be re-argued |
| A8 | Force-decode's rebuilt KV reaches a functionally equivalent end state | ⚠️ partial — S2 verified **sampled tokens** match at `F=64`; KV bit-identity is **not** available by construction (prompt KV came from *prefill*, force-decode rebuilds it in *decode*) | the A-vs-B race is not comparing one end state and the gate must change |
| A9 | Prompts can be generated to hit exact tokenized-length bins | ✅ **verified** — all 6 bins landed exactly on target, confirmed in each run's `PREFILL_LENS`. Was: to verify — `PREFILL_LENS` derives from tokenizing the prompt **text**, not from a label | bins must be found by search rather than construction |

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


## Run 2 INTERIM — 4 of 6 bins (2026-07-31). The affine model is in doubt.

Setting as in § 11. Each bin: all rounds at ONE payload, so `spread_pct` is a **noise estimate**.

| `L_p` | chunks | `band_bytes` | `mean_span_us` | `spread_pct` | rounds | lever verified |
|---|---|---|---|---|---|---|
| 256 | 1 | 9,437,184 | 46,149.6 | 0.003% | 4 | ✅ all 256 |
| 512 | 2 | 17,825,792 | 46,236.5 | 0.003% | 4 | ✅ all 512 |
| 1,024 | 4 | 34,603,008 | 56,141.0 | 0.002% | 4 | ✅ all 1,024 |
| 2,048 | 8 | 68,157,440 | 85,682.6 | 0.002% | 4 | ✅ all 2,048 |

`band_bytes` matched the code-derived value exactly in every bin. **Noise floor is 0.002–0.003%**, so the
gaps below are signal, not scatter.

**The marginal cost per byte is NOT constant — it worsens monotonically with payload:**

| segment | added bytes | added time | marginal |
|---|---|---|---|
| 1 → 2 chunks | +8.00 MB | **+0.087 ms** | 10.9 µs/MB = **96.5 GB/s** ⇐ impossible as a rate ⇒ fixed cost still dominates here |
| 2 → 4 chunks | +16.00 MB | **+9.905 ms** | 619 µs/MB = **1.694 GB/s** |
| 4 → 8 chunks | +32.00 MB | **+29.542 ms** | 923 µs/MB = **1.136 GB/s** |
| 1 → 32 chunks (run-1, two-point) | +248 MB | +292.1 ms | 1,178 µs/MB = **0.890 GB/s** |

⇒ **the shape is convex/super-linear, not affine.** Run 1's two-point fit assumed a constant slope; the
9.3% mid-range error it showed was the first sign, and this is the mechanism behind it. An affine fit on
these four points gives **R² = 0.9638** — still poor, and the residual pattern is systematic (not noise).

**But the intercept is stable and reproducible.** Affine fits on run 1 (2 points) and run 2 (4 points)
agree on the fixed cost to within 0.1%: **35.55 ms vs 35.59 ms**. So the *fixed* half of the model is
solid; it is the *slope* that is not a constant, and the slope is the half the cost model needs.

⚠️ **NOT CONCLUDING. 4 of 6 bins.** The remaining bins — 16 and 32 chunks — are precisely the ones that
set the top-end shape and therefore decide this. The marginal rate that the cost model needs is the one
at the payload sizes that matter, and it is **not yet measured**.

⚠️ **Self-correction:** an earlier line in this session quoted run-1's overall slope as "1.123 µs/MB".
That was a unit slip (s/B → µs/MB, off by 1000×). The correct figure is **1,178 µs/MB**; the GB/s
figures were unaffected.

**Infra note:** `s30_bin0512` attempt 1 died on **EPCC ingress gRPC 502** — the known signature, not a
config fault. Attempt 2 succeeded. Confirming this mattered: a config fault would have failed every
remaining bin identically.

## Run 2 — 5 of 6 bins. The shape is a POWER LAW, and here is the pre-recorded 32-chunk prediction

**Recorded 2026-07-31 05:03 UTC, while `s30_bin8192` was already running (PID 486524) and before any
32-chunk number existed.** Project rule: *predictions outside the fit range go in writing before the run.*

`s30_bin4096` landed at 04:59 UTC — `band_bytes = 135,266,304` (code-derived, exact), `mean_span_us =
169,891.091`, `spread_pct = 0.001%`, `rounds = 4`, all `prefill_len = 4096`.

| `L_p` | chunks | `band_bytes` | ingress ms | `spread%` | average µs/MB | marginal µs/MB |
|---|---|---|---|---|---|---|
| 256 | 1 | 9,437,184 | 46.150 | 0.003 | 4,890 | — |
| 512 | 2 | 17,825,792 | 46.236 | 0.003 | 2,594 | 10 |
| 1,024 | 4 | 34,603,008 | 56.141 | 0.002 | 1,622 | 590 |
| 2,048 | 8 | 68,157,440 | 85.684 | 0.003 | 1,257 | 881 |
| 4,096 | 16 | 135,266,304 | 169.891 | 0.001 | 1,256 | **1,255** |

**The marginal is still rising at 16 chunks** (590 → 881 → 1,255 µs/MB) and has only just caught up with
the average. Both facts kill the affine model: under `t = t0 + b/BW` the marginal is a *constant*.

**A 3-parameter power law fits essentially perfectly:**

```
t = 42.82 ms + 9.737e-12 · bytes^1.6131        R² = 0.999473, max residual 3.45%
```

versus affine on all five points (R² = 0.9754, residuals ±20%) or affine on the top three
(R² = 0.9935, residuals still systematic). **Exponent 1.613 ⇒ doubling the payload multiplies the
marginal cost per byte by 1.53×.**

⚠️ **This is a measured SHAPE, not an explained one.** A transport cost growing *faster* than payload is
not what a wire does. Candidate causes — contention, per-chunk work that itself scales with `L`, or
something inside the timed span that is not KV movement — are **not** distinguished by this data. Treat
`α = 1.613` as a fitted descriptor of the as-built path over 9.4–135 MB, not as a law.

### The prediction — three models, 33% apart, one run decides

| model | predicted 32-chunk (269,484,032 B) ingress |
|---|---|
| **power law `α = 1.613`** ⇐ the one I am betting on | **429.5 ms** |
| affine fitted on the top three points | 322.2 ms |
| pure per-byte at the current 8→16 marginal | 338.3 ms |

`s30_bin8192` (2 rounds, `L_p = 8192`) settles it. **If the answer comes in near 322–338 ms the power law
is wrong and the curve is flattening** — which would matter a great deal, because a flattening curve
means the reload lane stops getting worse and offload survives at large `L`.

**Why the exponent matters more than any single rate:** if `α > 1` holds, the reload lane's cost grows
*faster* than the KV it moves, so **every increase in `L` pushes the boundary toward recompute** — the
opposite of the intuition that bulk transfers amortise. If `α → 1`, the lane is merely slow, not
degenerate. The cost model's qualitative conclusion hangs on this, not on the headline GB/s.

## ✅ Run 2 COMPLETE, 6 of 6 — my prediction was WRONG, and the real shape is a hockey stick

`s30_bin8192` landed 05:16 UTC, **rc=0 on the first attempt** (`FINISH_DONE 06:17:39+01:00`).
`band_bytes = 269,484,032` (code-derived, exact), `mean_span_us = 338,266.277`, `spread_pct = 0.001%`,
`rounds = 2`, both `prefill_len = 8192`.

### The prediction test — I lost, and the naive model won exactly

| model | predicted | measured | error |
|---|---|---|---|
| **power law `α = 1.613`** ⇐ what I bet on | 429.5 ms | 338.3 ms | **+27.0%** ❌ |
| affine fitted on top-3 (4,8,16 ch) | 322.2 ms | 338.3 ms | −4.7% |
| **carry the 8→16 marginal forward** | **338.3 ms** | 338.3 ms | **+0.0%** ✅ |

**A power law with R² = 0.999473 over five points extrapolated 27% wrong one doubling outside its fit
range.** The simplest possible model — "assume the last marginal holds" — was exact. This is the cleanest
demonstration so far of why the project rule exists: *validating a model only where it was fit validates
nothing.* In-range fit quality carried **no** information about extrapolation here.

### What actually happens: the marginal saturates

| `L_p` | ch | MB/band | ingress ms | `spr%` | n | avg µs/MB | **marginal µs/MB** | marginal GB/s **per band** |
|---|---|---|---|---|---|---|---|---|
| 256 | 1 | 9.4 | 46.150 | 0.003 | 4 | 4,890 | — | — |
| 512 | 2 | 17.8 | 46.236 | 0.003 | 4 | 2,594 | 10.4 | 96.6 |
| 1,024 | 4 | 34.6 | 56.141 | 0.002 | 4 | 1,622 | 590.4 | 1.694 |
| 2,048 | 8 | 68.2 | 85.684 | 0.003 | 4 | 1,257 | 880.5 | 1.136 |
| 4,096 | 16 | 135.3 | 169.891 | 0.001 | 4 | 1,256 | **1,254.8** | **0.797** |
| 8,192 | 32 | 269.5 | 338.266 | 0.001 | 2 | 1,255 | **1,254.5** | **0.797** |

**Two independent payload doublings return the same marginal to 0.02%.** The marginal rose (10 → 590 →
881 → 1,255 µs/MB) and then **stopped dead**. It is not a power law; it is an approach to an asymptote.

**Above 8 chunks the path is purely proportional — no fixed cost left at all:**

```
affine on (8, 16, 32 chunks):  t = 0.18 ms + bytes / 0.7966 GB/s-per-band     R² = 1.000000
residuals: +0.01% / −0.00% / +0.00%
```

An intercept of **0.18 ms on an 85–338 ms span** is zero within measurement. So the real shape is a
**hockey stick**: a flat ~46 ms floor that ignores payload up to ~2 chunks, a knee between 2 and 8
chunks, then a clean straight line through the origin. Both earlier descriptions were wrong — "affine
with a 35.6 ms intercept" (4 bins) and "power law α = 1.613" (5 bins) were each the best fit to a
*truncated* curve.

### ⚠️ Unit correction — "aggregate" was mislabelled two turns ago

`band_bytes` is **per band, and there are 4 bands**; total payload is `4 × band_bytes`. Confirmed by
arithmetic that the harness cannot fake: `4 × band_bytes` = **34.0 MiB at `KV_META_LEN = 2`** and
**36.0 MiB at `KV_META_LEN = 4`** — i.e. exactly 32 MiB of KV plus a metadata term that tracks
`KV_META_LEN` 1:1.

⇒ **Every ingress marginal I have quoted in GB/s is PER BAND, not aggregate.** One table header two turns
ago said "aggregate over 4 streams" — **that label was wrong**; the numbers under it were right as
per-band figures. Aggregate is 4×:

- **saturated marginal = 0.7966 GB/s per band = 3.186 GB/s aggregate**
- retired S1 figure = 0.1931 per band = 0.7726 aggregate
- ⇒ **the retired average understates the true marginal by 4.13×** (run 1 said 4.61× from a two-point
  fit; the converged value is 4.13×)

Note the egress numbers use the *opposite* convention — `32 MiB × chunks` is already the **total**, so
those GB/s are aggregate. Two paths, two conventions, in the same `timing.json`. Worth remembering.

### What this gives the cost model — the reload lane, measured not extrapolated

At `L = 8192` a full prefix reload is **338.3 ms, measured directly** (it is the largest bin, not an
extrapolation). Against S2's measured forced token of 88.35 µs:

| lane at `L = 8192` | cost | source |
|---|---|---|
| **reload from host (H2D)** | **338.3 ms** | measured, this run |
| force-decode in place | 723.8 ms | 8,192 × 88.35 µs (S2-measured) |

⇒ **reload beats force-decode by 2.14× at `L = 8192`, as-built.** For contrast, ROADMAP's figures built
on the falsified rate said the reload lane cost **753 → 1390 ms**; it is **2.2–4.1× cheaper** than that.

⚠️⚠️ **This covers ONE HALF of the round trip.** It prices getting KV *back into* the device, and is
valid only where the host already holds a copy — i.e. **prompt KV under A6** (verified: `inj_{i}.npz` is
written and never deleted). The **decode→host offload half does not exist** (S3b, unbuilt), so this is
**not** a verdict on offload-vs-recompute for decode-produced KV. Per Le's instruction, that half stays
unjudged until there is a real implementation. **Needs Le's decision, not mine.**

## Free finding — PREFILL egress also degrades with payload (2026-07-31, zero extra wafer time)

⚠️⚠️ **SCOPE — read before using any number here.** This is the **prefill module's own KV egress path**
(the existing prefill→host bridge). It is **NOT** decode-side KV offload, and it must **not** be used to
price the offload lane. Le's instruction stands: *decode egress has to rely on a real implementation*
(S3b), and until that exists the offload half of the round trip is **not judged**. Recorded here because
it is (a) a free by-product of the 4 completed bins and (b) directly relevant to **M4**, which owns this
transport path.

Extracted from `per_req_kv_egress_ms` in the same four `timing.json` files. Payload here is the egress
payload, `32 MiB × chunks` (a different constant from ingress's `band_bytes`).

| `L_p` | chunks | payload | `per_req_kv_egress_ms` | average rate | marginal |
|---|---|---|---|---|---|
| 256 | 1 | 32 MB | 23.56 | **1.424 GB/s** | — |
| 512 | 2 | 64 MB | 74.73 | 0.898 GB/s | 0.656 |
| 1,024 | 4 | 128 MB | 181.79 | 0.738 GB/s | 0.627 |
| 2,048 | 8 | 256 MB | 458.56 | 0.585 GB/s | 0.485 |
| 4,096 | 16 | 512 MB | 820.76 | 0.654 GB/s | **0.741** ⇐ improves |
| 8,192 | 32 | 1,024 MB | 1,679.65 | 0.639 GB/s | 0.625 |

*(These rates are **aggregate** — egress payload `32 MiB × chunks` is already the total. Opposite
convention to ingress; see the unit correction above.)*

**Full 6-point egress marginals: 0.656 → 0.627 → 0.485 → 0.741 → 0.625 GB/s.** No trend — it wanders in
a 0.6–0.74 band with one dip at 8 chunks. Unlike ingress, egress has **no saturating structure and no
super-linearity**; it is roughly a constant ~0.63 GB/s aggregate with noise, plus the anomalously good
1-chunk point.

Three things worth keeping:

1. **The 1-chunk point reproduces the long-standing anchor to 0.3%.** ROADMAP's "1.426 GB/s aggregate,
   measured on `mtbench8`" comes out here as **1.424 GB/s** on a completely different prompt set. That is
   an independent confirmation of the S0 egress anchor — the harness measures what it says it measures.
2. **…and the anchor is only valid at its own payload.** By 8 chunks the average has fallen to
   0.585 GB/s — **2.4× worse than the anchor**. The concern that motivated this whole sweep ("a single
   payload point cannot give you a rate") is confirmed on the egress path too.
3. ⚠️ **CORRECTION to what I wrote at 4 bins.** I described egress as *monotonically* degrading, on the
   strength of 0.656 → 0.627 → 0.485. The 16-chunk point **breaks that**: the marginal comes back up to
   **0.741 GB/s**, the best since the first segment, and the average turns around too (0.585 → 0.654).
   **Egress is not monotone and its worst point is in the middle** — so it does *not* share ingress's
   shape, and the "both paths have the same disease" framing I used was premature. Ingress keeps
   degrading through 16 chunks; egress does not.

⇒ For M4: **quoting 1.426 GB/s as *the* egress bandwidth still overstates it at every payload above one
chunk** (the best any larger payload achieves is 0.741 marginal, about half the anchor). But the failure
mode is a mid-range dip, not runaway growth, so egress does not carry ingress's `α > 1` problem.

Not concluded: the mechanism, for either path — and now there is positive evidence they differ.

## A7 corroborated at the source, and the recorded prefix-cache ratios verified (2026-07-31)

Two loose ends from the A7 falsification, both closed from the Mooncake release, no wafer time.

**1. `input_length` semantics — the caveat I had left open is resolved.** The release README defines
`input_length` as "Number of input tokens", and its own worked example shows two requests with
`input_length` 6,955 and 6,472 **sharing the first 12 hash IDs = 6,144 tokens** of prefix. So
`input_length` is the *full* input including retained/shared prefix — exactly the quantity `L_p` needs.
⇒ The A7 falsification (`L_p` is 97.2% / 97.9% of tokens; 99.9% of requests have `L_p > L_g`) rests on
the right field, and the last reason to doubt it is gone.

**2. The prefix-cache ratios already in `topics/agentic-kv-trace-datasets.md` check out.** Recomputed
directly from the traces (block size 512, a block counts as reusable if its hash ID was seen earlier in
the trace):

| trace | requests | prefix blocks | reusable | ratio | previously recorded |
|---|---|---|---|---|---|
| `conversation_trace` | 12,031 | 288,500 | 105,710 | **36.6%** | ~40% |
| `toolagent_trace` | 23,608 | 409,616 | 226,316 | **55.3%** | ~59% |

Both within ~4 points of the recorded values — **corroborated, not falsified**. The small gap is expected
and in the right direction: my count is an *upper* bound with no eviction and unbounded history, so the
published figures being close means their cache model is not doing much work. Good enough to keep using
these as the reuse-rate inputs for scenario sizing.

## Last updated

2026-07-31

## Direction of the host-KV asymmetry — stated convention-free (2026-07-31)

The old claim "the uplink is 1.85× slower than the downlink" compared two single-payload **averages**.
With six payload points, and expressed as **milliseconds per 256-token chunk of KV** (so the
per-band vs total mismatch cannot distort it — both are "one chunk of the same request's KV"):

| direction | ms per chunk (16→32 segment) |
|---|---|
| H2D ingress (decode reload) | **10.52** |
| D2H egress (prefill offload) | **53.68** |

⇒ **egress is 5.10× SLOWER than ingress. The asymmetry runs the OTHER WAY** — the uplink is the fast
direction, not the slow one. Every conclusion drawn from "the slow direction is the uplink" is void.

⚠️⚠️ **Do NOT add these two into a round-trip cost.** The D2H figure is **prefill's** egress kernel on
prefill's layout; **decode-side offload does not exist**. An offload+reload round trip computed this way
is exactly the substitution Le ruled out — decode egress must rest on a real implementation (S3b).
The arithmetic was run and is deliberately **not recorded as a result**.

## S30 status: COMPLETE. What is left needs a decision, not a run.

All six bins landed; the ingress model is closed. Remaining S3 items and why none of them is
"just run it":

| item | blocker |
|---|---|
| **S3b** decode→host egress | **needs code written** (the path does not exist). Its promotion to *prerequisite* rested on A7, which is now falsified — so whether to build it at all is Le's call |
| **S3c** the A-vs-B race | needs S3b for the offload half; the reload half is already measured |
| **S2b** force-decode vs prefill | runnable in principle, but needs a decision on which `F` values and whether the prefill lane is still worth pricing |
| **S3a** `f(pos)` to 16,384 | **partly answered free** — decode cost fitted `623.62 µs + 28.34 ns × ctx`, R² = 1.0000 over contexts 1,290–14,344 from run-1 data, 7× beyond the original fit range. A dedicated run would mainly add a long-context *correctness* control |
| ROADMAP / PROGRESS | updated 2026-07-31 per the project rule "falsifies a written assumption → fix the affected doc immediately" |

## Long-context correctness: checked for free, and the answer is "this prompt set CANNOT tell us"

S30's design flagged a risk: the artifact had **never been exercised past ~3,407 tokens**, decode's RoPE
is an f32 recurrence with no assert watching drift, and long-context points would therefore need a
**correctness control, not only timing**. S30 blew straight past that ceiling — **13 of 22 requests ran
to the full compiled context of 20,480** (hitting the `MAX_OUTPUT_LEN` budget, `halted_eos = false`),
**6× beyond anything this artifact had done**. The generated text was already on disk, so this cost
nothing.

**Every one of those runs degenerates into a repetition loop.** distinct-4-gram over successive
1,000-word windows collapses from ~0.8–1.0 to **0.00–0.15** and stays there.

**But it is NOT a long-context defect, and the check that shows this is the one that matters:**

| where the loop starts (absolute context) | count |
|---|---|
| **inside the previously-verified range (< 3,407)** | **5 of 20** |
| earliest collapse | **ctx = 1,024** |

A RoPE-drift or long-context failure **cannot** begin at ctx = 1,024 — that is deep inside the range S0
reproduced **bit-identical against the HF oracle**. Worse (for the diagnosis, better for the hardware):
several runs collapse at almost exactly `ctx ≈ L_p` — `1024/2` at 1,024, `2048/1` at 2,048, `4096/1` at
4,096 — i.e. **the loop begins the instant generation starts**, before context depth can matter at all.

⇒ **The degeneration is prompt-driven, not device-driven.** The S30 prompts are *random word salad*
("Summarize the following document." + non-repeating filler chosen for exact token counts). Asking a
1.7B model to summarise noise and looping is ordinary LLM behaviour on out-of-distribution input.

### The two things this actually establishes

1. **No evidence of a long-context correctness defect — and no evidence against one either.** The
   confound is total: this prompt set cannot distinguish "the device is fine" from "the device is
   broken", because the *expected* output on noise is already degenerate. **This is not a passed
   correctness control; it is an inconclusive one.**
2. ⚠️ **S3a's long-context correctness control CANNOT be built on the S30 prompt set.** It needs
   **coherent** long prompts — real text (LongBench-v2 / SWE-bench are already on this machine) — where
   a sane continuation is distinguishable from a broken one. The exact-token-count generator that made
   S30 possible is precisely the wrong tool for S3a. Recorded now so S3a is not planned around it.

**None of the S30 timing results are affected.** The ingress span is measured per round *before*
decoding, and transport is content-blind by design — which was stated as reason (2) for choosing
synthetic prompts in the first place. That reasoning holds; it just does not extend to correctness.

## S3a's `f(pos)` curve, delivered free from the S30 bins — linear to the compiled ceiling

S3a's timing half turns out to be **already measured**. Every S30 round reports
`device_steady_us_per_tok` (device TSC) at a known prompt length, so each of the 22 rounds is a point on
the decode-cost curve. Because a round's steady tokens span `[L_p, L_p+g]`, and a linear marginal
`f(pos) = α + β·pos` averages to `α + β·(L_p + g/2)`, **fitting the round average against mean context
recovers the MARGINAL coefficients directly** — this is `f(pos)`, not just `f̄(L)`.

```
f(pos) = 623.70 µs + 28.315 ns × pos        R² = 0.99997,  n = 22
```

fitted over mean-context **1,136 → 14,336**, i.e. actual contexts up to the compiled ceiling of
**20,480**. Measured span: 655.6 µs/token at the low end, **1,028.5 µs/token at the top** — decode is
**1.57× slower** at the ceiling than at the anchor point, which no constant-cost model captures.

**Linear, with no detectable curvature anywhere in that range.** Three independent fits now agree:

| fit | range | intercept | slope |
|---|---|---|---|
| S0 (2026-07-28) | ~600–2,000 | 627.83 µs | 26.45 ns |
| run 1 (2026-07-31) | 1,290–14,344 | 623.62 µs | 28.34 ns |
| **all 6 bins, 22 rounds** | **1,136–14,336** | **623.70 µs** | **28.315 ns** |

The last two agree to **0.01% on intercept and 0.09% on slope** despite coming from different runs and
six different prompt lengths — that is an independent reproduction, not a re-fit of the same data.

### The methodological contrast worth keeping

**S0's anchor, fitted over ~600–2,000, extrapolates to ctx = 20,480 — a 10× reach — within +2.9%**
(1,170 µs predicted vs 1,204 µs from the full fit). On the same day, on the same machine, **the ingress
power law fitted over five points failed at 2× reach by +27%.**

So "extrapolation is unreliable" is *not* the lesson. The lesson is narrower and more useful:
**extrapolate a curve whose shape you can argue from mechanism, not one whose shape you inferred from
the fit.** Decode-per-token is linear in context because attention scans a KV cache that grows by one
token per step — the shape is predicted before any data. The ingress curve's shape was read off the
data, and the data was truncated.

⇒ **S3a's timing deliverable is complete** and needs no wafer time. What S3a still lacks is its
**correctness control**, which is blocked on a coherent-text prompt set (see the long-context section
above) — the timing half and the correctness half now have different blockers.

## ⛔ SUPERSEDED AS THE INDEX (2026-07-31)

Status and results now live in **`topics/m2-experiment-register.md`** (ContextBase: *M2 · Experiment
Register*). This file remains only as the **chronological narrative** of how conclusions were reached and
overturned; it is append-only and out of order.

**Two of its conclusions are retracted there:**

1. **"The uplink is 5.10× faster / the asymmetry is reversed"** (§§ 16–17) — **withdrawn.** It compared
   prefill's KV egress against decode's KV ingress. `prefill.csl:104` shows prefill's egress is a
   **switch-gather along X using `fft transpose.csl`** — a layout transform plus a many-PE→edge gather —
   while the ingress is a scatter with no transform. **Different operations; their rates are not
   comparable**, and decode's egress does not exist. There is now **no valid claim about which direction
   is faster.**
2. **A7's falsification** (§ 14) — **withdrawn.** It rested on Mooncake's `output_length`, which is
   **hard-capped at 2,000 tokens** (both traces; mean 182–343). A thinking model routinely exceeds that,
   so the trace structurally cannot represent long generation.

**The recurring error behind both:** turning a result into a conclusion before asking whether the two
things compared are the same kind of thing — and, when a result is surprising, suspecting the assumption
before suspecting the experiment. This file warns against exactly that in one section and commits it in
another.

## A7 — FINAL STATE (2026-07-31, supersedes both entries above)

The Mooncake-based falsification recorded earlier, and its subsequent withdrawal, are **both
superseded**. A7 is **falsified** on **TraceLab** — 665,453 real Claude Code/Codex rounds with
**uncapped** output (max 64,000; 6.0% exceed Mooncake's entire 2,000 cap): `L_p` is **99.7%** of all
tokens and only **12 of 665,453** rounds have `L_g > L_p`. Thinking is present in 37.8% of rounds but
is 12.7% of an output that is itself 0.3% of tokens.

Do not cite the Mooncake figures for this question — that trace's `output_length` is hard-capped and
cannot show long generation. Full record, including the scale gap (TraceLab mean input 171,576 tokens
vs our 20,480 context ceiling), in [[a7-Lp-vs-Lg-settled-on-tracelab]].

## E9 — `f_forced(pos)` DONE (2026-07-31, real WSE-3; recovered after the `m2-s3-0` session was lost)

The E9 run completed on CS-3 (~19:05) but the driving session (`m2-s3-0`) was destroyed before the
result was written anywhere. Recovered by re-reading the session transcript and re-analysing the raw
`timing.json` (survived in the old session scratchpad); every number below is bit-reproduced from that
file, not copied from prose. Canonical result now lives in the register (*M2 · Experiment Register*,
Ch.2 E9); this is the narrative of how it was measured and what the `F=1` control caught.

**Setup.** `serve_2x4_8k20k_e9` (2×4 blocks, 28 layers, `FORCED_MAX=20224`), 256-token prefix, 7 rounds
sweeping `F` = 1, 512, 1024, 2048, 4096, 8192, 20224. A TSC tic/toc was added around the forced segment
in `decode.csl` (+ `tsc_emitted` fix so the `F==N` terminator-emit path also reports); host fields
`fd_f_device` / `fd_span_us` / `fd_us_per_forced_tok` land in `decode_device.tsc.per_round[]`.

**Three pre-registered checks passed.** ① `fd_f_device` non-zero on all 7 rounds including r6 (`F==N`) —
the terminator path executed correctly on hardware (closes Codex's P1). ② r6 fastest round (2.37 s wall,
no free tail). ③ offset removed, doubling F scales span ×2.03…×2.20.

**The `F=1` control caught a contamination — the point of including it.** `fd_span_us` at F=1 = **22.03 ms
for ONE step** vs a ~88 µs steady forced step. That is a fixed per-round **pipeline-fill** offset (tic
fires before HT_tail has received the first Z), **additive on every round**, and distinct from
`kv_ingress_span_us` (46.15 ms, seven rounds identical, = E5's 1-chunk / 256-token reload). ⇒ the host
`fd_us_per_forced_tok` (whole span ÷ F) over-counts: **+58% at F=512**, −13% at F=20224. Without the F=1
round we'd have taken 117.0 µs as the position-512 cost (58% wrong). **"Look at the ratio, don't divide"
is exactly what this was designed to protect.** A warning comment was added at the forced-segment block
in `launch_decode.py`.

**Result — segment-differenced marginal (offset-immune):** 74.1 → 76.3 → 79.5 → 85.5 → 98.0 → **134.3**
µs/forced-token over positions 1→20,224. Two findings:
1. **Forced decode has its own `f(pos)` = 71.6 µs + 4.30 ns·pos** (R²=0.999, monotone rise). ⚠️ The
   slope is **4.30 ns/tok = only 0.15× free's 28.3** — the two lines are **NOT parallel**, forced is far
   flatter. (An interim writeup of this run said "lane A is quadratic, slope ≈ 30 ns/tok" — **both wrong**,
   corrected here.) ⇒ lane A = Σ f_forced is super-linear but **linear-dominated to the ceiling**: quad
   term 1.5% at L=512, 25% at 8192, crossover L≈33k > 20,480. **Measured lane A at F=8192 = 735 ms,
   within 1.6% of E3-constant × F (723.8 ms)** — so E3's 88.35 µs × F is a good lane-A model to 8192; it
   only diverges at the extreme (F=20,224: 2,350 vs 1,787 ms, +31%).
2. **forced/free ≈ 0.12** across a 55× position range (11.7%→13.0%), bracketing S2's single 13.50% and
   the old 11.7–12.0% mock prediction as a near-flat line. Mechanism verified in code: force-decode
   pipelines tokens through the 8 (2×4) block stages, but the ratio is set by
   `max_layers_per_block / n_layers = 4/28 = 1/7 ≈ 14.3%` (`layer_counts=[2,4,4,4,4,4,4,2]`), **not**
   1/N_blocks = 1/8; measured ratio rises toward that 14.3% asymptote. Refines ROADMAP's "~8.5×" (that
   was the short-context end 1/0.117).

⇒ **E10 (A/B crossing) is unblocked and needs no new code** — E9 forced curve vs E5 measured ingress.

## E10 — A/B crossing, PREDICTED from measured E5+E9 (2026-07-31; device-verify pending)

No new run needed to first order: A pays `laneA(L_hist+L_new)`, B pays `ingress(L_hist)+[laneA(L_hist+L_new)−laneA(L_hist)]`,
so **A−B = laneA(L_hist) − ingress(L_hist)** — `L_new` cancels and the boundary is purely "force-decode L_hist in
place vs reload its KV". Using E9's measured lane A and E5's measured ingress:

| L_hist | chunks | A rebuild (ms) | B reload (ms) | winner |
|--------|--------|----------------|---------------|--------|
| 512 | 2 | 37.9 | 46.24 | A |
| 1024 | 4 | 76.9 | 56.14 | B |
| 2048 | 8 | 158.3 | 85.68 | B |
| 4096 | 16 | 333.5 | 169.89 | B |
| 8192 | 32 | 735.1 | 338.27 | B |

**Crossing ≈ 700 tokens (~2.7 chunks)** — inside the pre-registered 400–1,500 window; model not falsified. Chart at
`assets/2026-07-31-e10-ab-boundary/e10_ab_boundary.svg`. ⚠️ This ASSUMES the `L_new` cancellation; the device run
must measure `lane B total − kv_ingress_span_us` against lane A's matching segment. **Blocked on:** CS-3 access
(not reachable this session) + a coherent three-region fixture (§3.1, not yet built — only `e9_fsweep`/`s30_bin*`
exist). If the reload leaves a warm-up/first-token penalty, the crossing moves right.
