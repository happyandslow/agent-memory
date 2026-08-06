# M2 · Experiment Register (index + results + three-lane design)

> **What this document is.** The single index of every M2 experiment: what it asks, what it plots, what data it uses, and what it found. **Chapter 1 is the table** — read it to see where we are. **Chapter 2 is the results**, one section per row, in the same order. **Chapter 3 is the design of the next experiments.**
>
> This is the **git authoritative copy**, mirrored one-way to ContextBase (*M2 · Experiment Register*, `X3DIdKV2s4`) and to agent-memory `topics/m2-experiment-register.md`. It **replaces the chronological tracker** as the place to look up progress; the old tracker (`topics/m2-s3-experiment-tracker.md`) is kept only as a **narrative of how conclusions were reached and overturned**.
>
> **Naming.** Experiments are `E<n>`. Old `S<n>` subtask ids are given for continuity; `E<n>` is canonical from now on.

---

# Chapter 1 — The experiment table

## 1.1 Done

| ID | Name | What it establishes | x-axis | y-axis | Data | Status |
|----|------|---------------------|--------|--------|------|--------|
| **E1** | Baseline reproduction *(S0)* | our numbers match the upstream pr14 line, bit-identical | — (table) | — | `mtbench8`, real WSE-3, n=2 | ✅ |
| **E2** | Ingress timer *(S1)* | a device-TSC pair on the KV ingress adaptor; the rate it produced was later falsified | — | — | `mtbench8` | ⚠️ superseded by E5 |
| **E3** | Force-decode port *(S2)* | force-decode works and is token-exact; cost of one forced token | — (single point) | — | `mtbench8`, `F=64` | ✅ |
| **E4** | Ingress payload discriminator *(S30 run1)* | does H2D KV load time depend on bytes at all? | payload (mixed within one run) | `spread_pct` of the round span | `s30_sweep`, 1 run × 8 rounds | ✅ |
| **E5** | Ingress payload curve *(S30 run2)* | the H2D reload cost model | KV bytes (1→32 chunks) | device-TSC ingress span (ms) | `s30_bin{0256..8192}`, 6 runs | ✅ |
| **E6** | Prefill egress payload curve | how prefill's own KV→host path scales | KV bytes (1→32 chunks) | `per_req_kv_egress_ms` | same 6 runs, free | ✅ |
| **E7** | Free-decode cost vs context | `f(pos)` — the compute baseline every lane is priced against | context position | µs per token | same 6 runs, free, n=22 | ✅ |
| **E8** | Long-context correctness | does output stay sane to ctx 20,480? | generated position | distinct-4-gram | same 6 runs, free | ⚠️ inconclusive |
| **E9** | `f_forced(pos)` *(S3)* | forced decode has its own f(pos); forced ≈ 0.12 × free; lane A ~linear to the ceiling | force-decode position | µs per forced token | fabricated session, `F` swept, real WSE-3 | ✅ |
| **E14** | Prefix × force-length sweep | separates prefix-dependent startup from steady forced-token cost; turns the ~700-token crossing into a boundary surface | prefix `P`, forced length `F` | forced span and marginal µs/token | `P={256,1024,4096,8192}` × `F={1,256,512,1024,2048,4096}`, real WSE-3, n=1 | ✅ model measured; direct boundary witnesses pending |

## 1.2 Planned — the three-lane race

**The scenario, fixed.** One request is evicted from the decode kernel, then resumes after new context arrives. Modelled on a long-running coding-agent session. Three regions, each independently varied:

| region | meaning | assumed state at resume |
|--------|---------|-------------------------|
| `L_hist` | everything said before this turn | KV already in host DRAM (computed in earlier turns) |
| `L_new` | the newly arrived context — user message, tool result, sub-agent return | not yet computed |
| `L_gen` | tokens generated after resume | held small and fixed so it cannot confound |

**The three lanes:**

| lane | what it does at resume | cost structure |
|------|------------------------|----------------|
| **A · rebuild everything** | KV was discarded at eviction. Force-decode all of `L_hist + L_new` in decode | `Σ f_forced(pos)` over `[0, L_hist+L_new]` — no transport |
| **B · reload + rebuild the delta** | Load `L_hist` KV from DRAM into decode, then force-decode only `L_new` | `ingress(L_hist)` + `Σ f_forced(pos)` over `[L_hist, L_hist+L_new]` |
| **C · compute the delta in prefill** | Give prefill the `L_hist` KV, prefill `L_new`, send the delta KV back, load it into decode | `move(L_hist→prefill)` + `prefill(L_new given L_hist)` + `move(delta→decode)` + `ingress(L_hist+L_new)` |

| ID | Name | What it establishes | Status |
|----|------|---------------------|--------|
| **E9** | `f_forced(pos)` | does a forced token cost more as context grows? | ✅ done — see Ch.2 E9 |
| **E10** | Lane A vs Lane B (resume latency) | the first resume-latency boundary: at what `L_hist` does reloading beat rebuilding? | ✅ **crossing ≈ 700 tok; `L_new` cancellation VALIDATED on real WSE-3 (ratio 0.97–1.00 across 512→8192), kv_ingress = E5 exactly (Ch.2 E10)** |
| **E11** | Full re-prefill baseline | re-prefill from scratch + ship all KV — a measurable substitute for lane C, conclusive one direction only | ⬜ |
| **E12a** | Resident-prefix Lane C compute screening | does prefill compute the delta faster than forced decode when history is already resident? | ⚠️ **screening negative** — compute alone loses 3.82–10.77×; exact pdSeparate port remains optional confirmation |
| **E12b** | Prefill-side KV ingestion | completes the missing host→prefill transport for true Lane C | ⏸ gated — do not build for the current host-mediated design unless exact E12a overturns the screening result |
| **E13** | Decode-side KV egress | a build — the offload half of lane B; the recurring cost E10 assumes away | ✅ **Step 1 DONE — Gate 1/2 PASS + Fig E-1 (Ch.2 E13); Gate 3 remains** |

## 1.3 What is measurable today, and what is not

```
prefill produces KV --[E6: egress, measured]--> host DRAM --[E5: ingress, measured]--> decode
                                                                                          |
decode produces KV --[E13 Step 1: egress, MEASURED — Fig E-1, 2026-08-03]--> host DRAM ----+

host DRAM ---------------- X no path into prefill (E12) X ---------------> prefill
```

⇒ **Lane A and Lane B are measurable now. Lane C is not end-to-end measurable**, but its resident-prefix compute half has now been screened on WSE-3 and is already slower than Lane B's forced delta before transport (E12a screening, Ch.2). E11 remains the full re-prefill substitute; E12b is gated. ⇒ E10 measures the **resume** cost only. The **eviction** cost (decode→host) needs E13.

## 1.4 Lane C: what `nc_service` already has

Surveyed 2026-07-31. `nc_service` is **already a Cerebras WSE-3 codebase** — CSL + Cerebras SDK end to end, no GPU, no vLLM/SGLang, no paged attention, no block tables. Not a port across architectures; joining two pieces that already exist.

**The decisive finding:** `kernels/qwen3_1p7b-prefill/src/prefill.csl` already implements chunked prefill over a resident on-chip KV prefix (FlashAttention-2 cross-chunk folding). Chunk `c`'s queries attend chunks `0..c` read out of `K_cache_bank`/`V_cache_bank`; the causal mask applies only to the diagonal pair, so earlier chunks are unmasked — exactly prefix semantics. ⇒ "compute new tokens on top of an existing KV prefix" is already device-proven maths. What is missing is a way to *fill* those banks from outside, plus a base-position offset.

| piece | state |
|-------|-------|
| attention over a resident prefix | ✅ already implemented and device-proven |
| prefill→prefill KV format | ✅ no transpose — `kv_egress_colmux` ships `K_cache_bank` verbatim (unlike prefill→decode, which does need one) |
| host can read the bank | ✅ `launch.py:1579` already does `read_symbol(..., "K_cache_bank")`; the symmetric `set_symbol` seed is the cheapest bring-up path — makes E12a possible with no fabric work |
| `LOAD_PREFIX`/`RESUME` + `cache_len` command ABI | ✅ exists (8-word `uint32`), proven on decode. Reuse verbatim; add a third command |
| fabric ingress template | ✅ `kv_ingress_adaptor` + `kv_ingress_injector` (~280 CSL lines), the mirror image of `kv_egress_colmux` — same switch column, reversed |
| transport seam | ✅ `KvTransport` Protocol (TCP ~9 GB/s, RDMA ~12.3 GB/s measured), opaque bytes keyed by `request_id` |
| what genuinely needs writing | prefill-side ingress landing KV in the banks + a base-chunk offset threaded through `current_chunk` (reset to 0 at `prefill.csl:1538`), `request_n_chunks`, the RoPE fill, host `attn_mask`, egress `rnc` accounting, and the `z_drain`/last-token machinery |

⚠️ Prefix length is bounded by **per-PE SRAM**, not a host page pool (`max_layers_per_block × max_n_chunks × kv_tile_size` fp16 on chip) — *more* restrictive than a GPU pool. Prefix must be chunk-aligned; `bsz == 1` throughout.

⇒ **Plan change:** lane C moves from "needs a decision" to **planned**, split into **E12a** (compute half, host-seeded, no CSL ingress) and **E12b** (fabric ingress). E12a first — it answers whether lane C's compute is even cheaper than force-decoding the delta, before any transport work.

## 1.5 Result column — what each planned experiment will present

| ID | Name | Result — what it presents | Status |
|----|------|---------------------------|--------|
| **E9** | `f_forced(pos)` | the fit `f_forced(pos)=α+β·pos`; verdict on lane A's shape | ✅ **DONE — β=4.30 ns/tok (0.15× free), forced≈0.12×free; lane A ~linear to ceiling. E10 next** |
| **E10** | Lane A vs Lane B | the crossing point, plus two separate segments (reload overhead, post-ingress forced-token cost) so the `L_new` cancellation is tested, not assumed | ✅ ≈700 tok; cancellation measured 0.97–1.00 across L_hist (Ch.2 E10) |
| **E11** | Full re-prefill baseline | whether full re-prefill ever beats A or B. Conclusive one direction only | ⬜ |
| **E12a** | Lane C compute, resident-prefix screening | is prefilling the delta actually cheaper than force-decoding it? | ⚠️ **screening negative** — 292.935 ms for 256-token delta, 409.636 ms for 1,024; compute alone is 10.77× / 3.82× forced. Exact pdSeparate port remains optional confirmation |
| **E12b** | Lane C transport (prefill KV ingress) | the prefill-side analogue of E5; completes lane C | ⬜ build |
| **E13** | Decode-side KV egress | the recurring eviction cost E10 assumes away; also the equivalence control for the history-provenance confound | ✅ **Step 1 DONE (Gate 1/2 + Fig E-1); Gate 3 remains** |

## 1.6 Run order

| # | run | new code? | why here |
|---|-----|-----------|----------|
| 1 | **E9** | no | zero-code; every E10 prediction depends on it → **done** |
| 2 | **E10** | no — force-decode + E5 ingress already timed | the actual boundary; both lanes measurable today |
| 3 | **E11** | no | free comparison point from the same fixture |
| 4 | **E12a** | screening used existing S6a `START_CHUNKS`; exact pdSeparate port still needs code | screening says no: compute alone loses 3.8–10.8×; port only for final confirmation |
| 5 | **E12b / E13** | yes, real | only for whichever lane E10/E12a show is live |

---

# Chapter 2 — Results

## E1 · Baseline reproduction ✅

Real WSE-3, `pdSeparate`, `serve_2x4_8k20k`, real weights, n=2. All 242 `timing.json` leaf fields reproduce upstream to ≤0.02%; all deviation host-side. Decode steady **654.95 / 655.10 µs**, prefill span **56.91 ms**, egress **23.49 / 23.56 ms**. ⚠️ Read only `agg_steady` / `per_round[]`; `tsc.*` outside `per_round[]` describes the last round only (3.4% error on `tok_per_s`).

## E2 · Ingress timer ⚠️ superseded

Added a device-TSC pair because no host-side timer on this SDK can see the H2D wire (`task_wait` on a nonblock send reports 51.15 GB/s = 4.5× the ceiling). Reported 0.7726 GB/s. **That number was not a rate** — the marker is correctly placed but the divisor was a single payload point on the flat part of what E5 showed is a hockey stick. True marginal is 4.13× larger.

## E3 · Force-decode ✅

`F=64`, 8 requests, **10,067 tokens bit-identical** vs the free-decode reference. Skip gate proven active. **One forced token = 88.35 µs = 13.50% of a free token.** ⚠️ Measured at `F=64` on short contexts only — E9 tests whether it holds at large `F`.

## E4 · Ingress payload discriminator ✅

One run, 8 rounds spanning 1→32 chunks. Predictions: per-step → `spread_pct ≈ 0.005%`; per-byte → `≈ 2,756%`. **Measured 243.834%.** Both wrong; ingress *is* payload-dependent but not proportionally.

## E5 · Ingress payload curve ✅ — the main transport result

| `L_p` | chunks | MB total (4 bands) | ingress ms | marginal GB/s (aggregate) |
|-------|--------|--------------------|------------|---------------------------|
| 256 | 1 | 37.6 | 46.150 | — |
| 512 | 2 | 71.3 | 46.236 | 386 *(floor artifact)* |
| 1,024 | 4 | 138.4 | 56.141 | **6.78** *(knee — E10D lands here)* |
| 2,048 | 8 | 272.9 | 85.684 | 4.54 *(knee)* |
| 4,096 | 16 | 541.2 | 169.891 | **3.19** *(saturated)* |
| 8,192 | 32 | 1,078 | 338.266 | **3.19** *(saturated)* |

**Hockey stick.** Flat ~46 ms floor below ~2 chunks, a knee, then a line through the origin: `t = 0.18 ms + total_bytes / 3.186 GB/s`, R²=1.000000 above 8 chunks. The marginal **decreases** with chunk count — not because the wire slows, but because the fixed ~46 ms floor is divided out: at low payload each byte rides nearly free inside the floor (the 1→2 marginal of 386 GB/s is a floor artifact), and the marginal only converges to the true transfer rate once the floor is paid off. **Saturated bandwidth = 3.186 GB/s (aggregate; two doublings return the same value to 0.02%).** ⚠️ A power law fitted to the first five points (R²=0.999473) mispredicted the sixth by +27%; "carry the last marginal forward" was exact. In-range fit quality carried no information about extrapolation.

## E6 · Prefill egress payload curve ✅ — and it does not transfer to decode

| chunks | payload | `per_req_kv_egress_ms` | average GB/s | marginal |
|--------|---------|------------------------|--------------|----------|
| 1 | 32 MB | 23.56 | **1.424** | — |
| 2 | 64 MB | 74.73 | 0.898 | 0.656 |
| 4 | 128 MB | 181.79 | 0.738 | 0.627 |
| 8 | 256 MB | 458.56 | 0.585 | 0.485 |
| 16 | 512 MB | 820.76 | 0.654 | 0.741 |
| 32 | 1,024 MB | 1,679.65 | 0.639 | 0.625 |

*(aggregate — egress payload `32 MiB × chunks` is already total, the opposite convention to E5's per-band `band_bytes`.)* The 1-chunk point reproduces the 1.426 GB/s anchor to 0.3%, but holds only at its own payload. ⚠️⚠️ **RETRACTED (2026-07-31): the claim this reverses the host-path asymmetry.** `prefill.csl:104` shows prefill's egress is a switch-gather along X using `fft transpose.csl` — a layout transform + many-PE→edge gather; E5's ingress is a scatter with no transform. Different operations; rates not comparable. Decode's egress does not exist.

## E7 · Free-decode cost vs context ✅

`f(pos) = 623.70 µs + 28.315 ns × pos`, R²=0.99997, n=22, over mean-context 1,136→14,336 (actual contexts to the 20,480 ceiling). 655.6 µs/tok low end, **1,028.5 µs/tok at the top — 1.57× slower**. Fitting round-average against mean context recovers the marginal coefficients, so this is `f(pos)`. Three independent fits agree to 0.01%/0.09%.

## E8 · Long-context correctness ⚠️ INCONCLUSIVE — do not cite as validation

13 of 22 requests ran to full 20,480 ctx (6× beyond anything this artifact had done); all degenerate into repetition loops. **But not a device finding** — 5 of 20 begin looping at ctx < 3,407 (inside the range E1 reproduced bit-identical), several at ctx ≈ `L_p`. The prompts are random word salad. ⇒ No evidence of a long-context defect, and none against one. A real control needs coherent long prompts.

## E9 · `f_forced(pos)` ✅ — forced has its own f(pos); forced ≈ 0.12 × free; lane A ~linear to the ceiling

Real WSE-3, `serve_2x4_8k20k_e9` (2×4 blocks, 28 layers, `FORCED_MAX=20224`), 256-token prefix, 7 rounds sweeping `F` = 1, 512, 1024, 2048, 4096, 8192, 20224. **Recovered from the lost `m2-s3-0` session** — raw `timing.json` re-analysed, numbers bit-reproduced (2026-07-31); the run completed on CS-3 ~19:05.

![E9 — forced vs free (µs/token and tok/s) vs context](../../assets/2026-07-31-e9-forced-curve/e9_forced_vs_free.svg)

**Three pre-registered checks passed.** ① `fd_f_device` non-zero on all 7 rounds including r6 (`F==N`=20,224) — the terminator-emit path (`tsc_emitted` fix, Codex's P1) executed correctly on hardware. ② r6 fastest round (2.37 s wall — all-forced, no free tail). ③ offset removed, doubling `F` scales the span ×2.03…×2.20.

**The `F=1` control caught a contamination.** `fd_span_us` at `F=1` = **22.03 ms for ONE step** vs a ~88 µs steady forced step. E14 and a source audit supersede the original description of this as a fixed pipeline-fill offset: the device tic fires after the `[N,F]` header but before HT_tail receives its first Z, and that header comes from one locally-ready west-edge result sender rather than an all-PE ready barrier. The span can therefore include prefix-dependent residual KV receive/copy, ingress-to-broadcast rebinding, round reset, and cross-PE readiness skew, in addition to first-token pipeline fill and final tail. It is distinct from `kv_ingress_span_us` (46.15 ms, seven rounds identical, = E5's 1-chunk / 256-token reload). ⇒ the host `fd_us_per_forced_tok` over-counts — **+58% at `F=512`**, −13% at `F=20224`. Without the `F=1` round we'd have taken 117.0 µs as the position-512 cost (58% wrong). A warning comment was added at the forced-segment block in `launch_decode.py`.

**The result — segment-differenced marginal (offset-immune):**

| position range | µs / forced token | forced/free ratio |
|----------------|-------------------|-------------------|
| 1 → 512 | **74.1** | 11.6% |
| 512 → 1,024 | 76.3 | 11.7% |
| 1,024 → 2,048 | 79.5 | 11.8% |
| 2,048 → 4,096 | 85.5 | 11.9% |
| 4,096 → 8,192 | 98.0 | 12.2% |
| 8,192 → 20,224 | **134.3** | 13.0% |

Two findings for the cost model:

1. **Forced decode has its own `f(pos)`:** `f_forced(pos) = 71.6 µs + 4.30 ns·pos`, R²=0.999, monotone 74→134 µs. But the slope is **4.30 ns/tok = 0.15× free's 28.3** — the two lines are **NOT parallel**, forced is far flatter (E9's own §3.4 prediction of a parallel 28.3 ns/tok slope is refuted). ⇒ lane A = Σ f_forced is **super-linear but linear-dominated across the whole reachable range**: the quadratic term is 1.5% of the linear at L=512, 25% at 8192, and the two are equal only at L≈33,000 — beyond the 20,480 ceiling. **Measured lane A at F=8192 = 735 ms, within 1.6% of E3-constant × F (723.8 ms).** So **E3's 88.35 µs × F models lane A to ~1.6% up to 8192** (the §3.4 "quadratic envelope → 1420 ms" is refuted); it diverges only at the extreme (F=20,224: 2,350 ms measured vs 1,787 ms constant, +31%). Falsifier bucket: β=4.3 ns/tok < 10 ⇒ the "E3-constant safe to multiply" branch, with the caveat that a single constant is a ±40% approximation on *per-token* cost across 0–20k even though the *integral* stays ~linear.
2. **forced/free ≈ 0.12** across a 55× position range (11.6%→13.0%), bracketing S2's single 13.50% and the earlier mock 11.7–12.0% as a near-flat line — far stronger than any single point. Cost model can write **`forced ≈ 0.12 × free(pos)`**. Mechanism verified in code: force-decode pipelines tokens through the **8 (2×4) block stages**, but the ratio is set by `max_layers_per_block / n_layers = 4/28 ≈ 14.3%` (`layer_counts=[2,4,4,4,4,4,4,2]`), **not** 1/N_blocks = 1/8; the measured ratio rises toward that 14.3% asymptote as context grows. Refines ROADMAP's "~8.5×" (the short-context end, 1/0.117).

⇒ **E9 done; E10 (A/B crossing) is next and needs no new code** — E9 forced curve vs E5 measured ingress.

## E10 · Lane A vs Lane B ✅ — crossing ≈ 700 tokens, cancellation VALIDATED on real WSE-3

The boundary is `A−B = laneA(L_hist) − ingress(L_hist)` — the `L_new` term cancels **iff** force-decoding `L_new` costs the same after a fresh rebuild (A) as after a KV reload (B). E5 (ingress) and E9 (`f_forced`) already price the two halves; **E10's device runs test that cancellation.** Ran 5 fixtures on real WSE-3 (2026-08-01, `serve_2x4_8k20k_e9`, reuse e9 store), each: prefill an `L_hist` prefix → reload its KV → force-decode, with rounds `F=[1, N]` (offset control + full budget, no free tail).

![E10 — Lane A (recompute) vs Lane B (reload), measured; cancellation validated](../../assets/2026-07-31-e10-ab-boundary/e10_ab_boundary.svg)

| `L_hist` | chunks | `kv_ingress` (reload, ms) | E5 | ratio | lane-B forced (µs/tok) | E9 `f_forced` | cancel |
|--------|--------|--------------------------|------|-------|------------------------|--------------|--------|
| 512    | 2      | 46.24  | 46.24  | **1.000** | 116.57 | 116.71 | 0.999 |
| 1,024  | 4      | 56.14  | 56.14  | **1.000** | 115.81 | 117.82 | 0.983 |
| 2,048  | 8      | 85.69  | 85.68  | **1.000** | 117.84 | 120.02 | 0.982 |
| 4,096  | 16     | 169.89 | 169.89 | **1.000** | 121.82 | 124.43 | 0.979 |
| 8,192  | 32     | 338.27 | 338.27 | **1.000** | 129.54 | 133.24 | 0.972 |

**Two things validated on device:** (1) `kv_ingress` (the reload) reproduces E5's ingress curve to **1.000 at every `L_hist`** — the reload path IS the E5 path. (2) lane-B's forced-token cost == E9's `f_forced` to **0.97–1.00** across 512→8192 (a slight ~3% dip at 8192, within fit/window error) ⇒ **the reloaded prefix length does not change downstream forced cost ⇒ `L_new` cancels.**

⇒ The boundary `laneA(L_hist) = ingress(L_hist)` now stands on measured ground. **Crossing = 700 tokens (~2.7 chunks):** below it, recomputing the prefix in place (A) beats E5's ~46 ms reload floor; above it, reload (B) wins and pulls away. Inside the pre-registered 400–1,500 window — **model not falsified.**

### E10D · direct A/B head-to-head ✅ — the winner FLIPS across the crossing, BOTH options measured on WSE-3

A skeptic-proof, fully-**measured** head-to-head: run both options end-to-end and show the winner flip. **Both columns are now direct device measurements** (2026-08-01, `serve_2x4_8k20k_e9`; Option-1 = recompute-in-place `fd_span(F) − offset`; Option-2 = `kv_ingress + post-ingress-forced(L_new)`).

![E10D direct flip — both options measured; A wins below the crossing, B above](../../assets/2026-07-31-e10-ab-boundary/e10d_direct_flip.svg)

| `L_hist` | Option-1 recompute (**measured**) | Option-2 reload (**measured**) | winner | predicted |
|--------|-----------------------------------|--------------------------------|--------|-----------|
| **512** (below ~700) | **57.32 ms** `[recompute(768)]` | **65.29 ms** `[ingress 46.24 + delta 19.05]` | **A recompute** | A ✓ |
| **1,024** (above ~700) | **96.96 ms** `[recompute(1280)]` | **76.31 ms** `[ingress 56.14 + delta 20.17]` | **B reload** | B ✓ |

⇒ **The flip is confirmed with all-measured data:** below the crossing recompute-in-place wins (57.3 < 65.3); above it reload wins (76.3 < 97.0). The `L_new`=256 delta costs the same in both lanes (19–20 ms) — a bonus cancellation confirmation. The directly-measured recompute (57.3 / 97.0 ms) landed within ~2% of the E9 fit (56.2 / 95.1) that stood in earlier — the fit was slightly low but the verdict is identical. **The ≈700-token option-1/option-2 boundary is now validated both ways and fully measured** — the component/cancellation test (E10) and the direct total-latency head-to-head (E10D).

## E14 · Prefix × force-length sweep ✅ — startup depends on prefix; steady cost depends on absolute position

**Question.** E9 fixed the starting prefix at 256 tokens. E14 asks whether its ~22 ms startup offset and E10's ~700-token A/B boundary survive when both the existing prefix and force-decode length vary.

**Run and evidence.** Real WSE-3, real Qwen3-1.7B weights, 2×4 blocks, 24 rounds over `P={256,1024,4096,8192}` × `F={1,256,512,1024,2048,4096}`; TSC converted at **0.85 GHz**. Device verdict passed 7/7 checks and all 24 prefill/decode rounds; the downloaded bundle passed 6/6 hash checks. Build job `wsjob-8sw57nu5dcdyycpb3eyfbr` and measured serve job `wsjob-ne6h4kkcywcvd88jsc2cds` succeeded. **n=1 only:** two repeat attempts ended at the EPCC ingress with HTTP/2 502; one wafer job succeeded but returned no downloadable evidence bundle, so it was deliberately not counted.

### Result 1 — the F=1 startup is prefix-dependent

| prefix P | F=1 span | F=256 span | KV ingress |
|---:|---:|---:|---:|
| 256 | 22.037 ms | 40.915 ms | 46.150 ms |
| 1,024 | 26.426 ms | 46.419 ms | 56.141 ms |
| 4,096 | 110.389 ms | 125.344 ms | 169.890 ms |
| 8,192 | 224.211 ms | 247.995 ms | 338.268 ms |

The old ~22 ms “fixed offset” is only a `P=256` fact. Treating it as universal contaminates long-prefix marginal estimates.

### Result 2 — after startup, all prefixes collapse onto one position curve

Including every adjacent-F segment gives a poor fit (R²=0.765787, RMSE 7.076 µs/token); every large residual comes from the first `F=1→256` transition. Restricting to the 16 steady segments with `F_lo≥256` gives:

`f_forced(position) = 71.745198 µs + 0.004093307 µs × position`

R²=0.997447, RMSE=0.681 µs/token, max residual=1.833 µs/token. This is close to E9's fixed-`P=256` curve (71.6 µs + 4.30 ns×position). **Steady forced-token cost is explained by absolute position; how that position is split between initial prefix and already-forced tokens adds no material term.**

For `F≥256`, use the two-piece model:

`D(P,F)=D(P,256)+Σ[q=P+256…P+F−1](71.745198 µs + 0.004093307 µs×q)`

where `D(P,256)` is a measured, prefix-dependent startup anchor.

### Result 3 — the A/B boundary is a surface, not ~700 everywhere

For matched final context and `L_new=256`:

- Lane A: `A(S,H)=D(S,H+L_new)`
- Lane B, delta reload: `B_delta=I(H)+D(S+H,L_new)`
- Lane B, full-context reload: `B_full=I(S+H)+D(S+H,L_new)`

| starting prefix S | delta-reload crossing H* | full-reload crossing H* |
|---:|---:|---:|
| 256 | 744 | 932 |
| 1,024 | 1,079 | 2,756 |
| 4,096 | 864 | no crossing for H∈[256,4096] |

Thus E10's ~700 result is the `S=256`, delta-reload slice of `H*(S,reload_policy,L_new)`, not a universal scalar. These crossings are **model-derived interpolations, not direct A/B witnesses**; no `S=8192` boundary is reported because the measured startup-anchor range leaves no `S+H` room.

### Result 4 — physical span decomposition and how the regression is obtained

The measured device interval is best written as

`T_observed(P,F) = T_ready(P) + T_fill(P) + T_steady(P,F) + T_tail(P+F-1)`.

In the earlier three-term shorthand, `T_fd = T_steady + T_tail`; it is not `F` identical token costs. The four terms have distinct meanings:

- `T_ready(P)`: work after the timer starts but before the first token can enter a globally ready pipeline. The implementation starts timing after one west-edge PE emits the `[N,F]` header, before HT_tail blocks on its first Z; other PEs can still be receiving/copying KV, flushing OQ7, rebinding ingress to broadcast, resetting the round, or arriving at the ready state.
- `T_fill(P)`: latency for the first forced token to traverse all 28 transformer layers. With stage layer counts `[2,4,4,4,4,4,4,2]`, a useful estimate is `T_fill(P) ≈ (28/4) II(P) = 7 II(P)`.
- `T_steady(P,F)`: the `F-1` completion intervals after the first token. If `II(q)=a+bq`, then
  `T_steady(P,F)=Σ[j=1…F-1] II(P+j)`
  `=(F-1)a+b[(F-1)P+F(F-1)/2]`.
  There are `F-1`, not `F`, intervals because the first completion is accounted for by readiness plus pipeline fill.
- `T_tail(q)`: final-token drain/post-processing after the last steady interval. Combining the free-decode fit with the eight-stage estimate gives `T_tail(q)≈f_free(q)-7II(q)=121.484 µs-0.000338 µs×q`, about 0.12 ms over this range.

The steady regression is computed directly from adjacent measured spans, without subtracting `F=1`. For every segment with `F_lo≥256`, define

`y_i = [D(P,F_hi)-D(P,F_lo)]/(F_hi-F_lo)`

and place that average at the segment's mean absolute position

`x_i = [(P+F_lo)+(P+F_hi-1)]/2`.

The four prefixes times four adjacent segments give 16 `(x_i,y_i)` observations. Unweighted least squares on `y=a+bx` yields `a=71.745198 µs/token` and `b=0.004093307 µs/position = 4.093307 ns/position`.

Using `T_fill≈7II` and the tail estimate, the `F=1` readings imply the following residual readiness costs:

| P | fill | tail | inferred ready |
|---:|---:|---:|---:|
| 256 | 0.510 ms | 0.121 ms | 21.406 ms |
| 1,024 | 0.532 ms | 0.121 ms | 25.774 ms |
| 4,096 | 0.620 ms | 0.120 ms | 109.649 ms |
| 8,192 | 0.737 ms | 0.119 ms | 223.355 ms |

The large prefix dependence is therefore overwhelmingly in pre-first-token readiness, not transformer pipeline fill. Readiness inferred independently from `F=256` differs by `+0.182,+0.495,-7.749,-3.195 ms`, showing round sensitivity and why `D(P,256)` remains the robust empirical anchor. That anchor plus the steady curve predicts every measured `F=512…4096` point within 0.90 ms. Exact identification needs one additional same-PE timestamp immediately after the first Z receive; the existing 16-u32 TSC burst has three padding words that can carry it.

**Next gates.** Resolve startup with `F={1,16,32,64,128,256}` by prefix; obtain n=2 after ingress stabilizes; then directly witness `S=1024,H={1024,1280}` and `S=4096,H={768,1024}`, `L_new=256`.

## E12a screening · Resident-prefix incremental prefill ✅ — compute alone loses to Lane B

**Question.** If the history KV is already resident on the prefill wafer, is computing only `L_new` in prefill cheap enough to justify Lane C? The tested resume model is:

```
Lane B = I_decode(L_hist) + F_forced(L_new | L_hist)
Lane C = P_resident(L_new | L_hist) + E_prefill(L_new) + I_decode(L_hist + L_new)
```

Assumptions for the estimate: prefill and decode are separate wafers with separate hosts; host-to-host time is zero; history KV is already resident on prefill; decode is repopulated with the full `L_hist + L_new` KV; prefill egress sends only delta KV; the three Lane-C phases are serial unless the explicitly labelled overlap lower bound is used.

### Existing full-prefill sweep — exact pdSeparate `6ecb496`

The six S30 artifacts already contain a complete device-TSC prefill curve; no rerun was needed. TSC is the device forward span, not host-wall.

| full prefill length | device forward | average µs/token | E6 KV egress |
|---:|---:|---:|---:|
| 256 | 56.909 ms | 222.30 | 23.564 ms |
| 512 | 74.466 ms | 145.44 | 74.730 ms |
| 1,024 | 113.954 ms | 111.28 | 181.791 ms |
| 2,048 | 210.461 ms | 102.76 | 458.563 ms |
| 4,096 | 473.610 ms | 115.63 | 820.757 ms |
| 8,192 | 1,280.425 ms | 156.30 | 1,679.655 ms |

This curve is useful context but is **not** `P(L_new | resident L_hist)`: dividing a full-prefill span by token count hid the large per-request floor and led to the earlier, over-optimistic 26–40 ms estimate for a 256-token delta.

### Resident-prefix WSE-3 screening run — 2026-08-02

The committed pdSeparate tree `6ecb496` does not contain `START_CHUNKS`, so it cannot directly execute resident-prefix prefill without a port. To avoid the other active session's dirty tree, the screening run used an isolated `git archive` of the already device-validated S6a commit `e0a19fc` (`models/qwen3_1p7b-prefill`). No active checkout was edited.

Configuration: real WSE-3; Qwen3-1.7B real dimensions; 512×1024 PEs; 2×4 logical blocks; 28 layers; `CHUNK_SIZE=256`; total context 8,192. Each fixture ran `START_CHUNKS=[0,k,k]`: one cold reference followed by two identical warm rounds. Device TSC starts at kickoff and ends at logits emit, excluding host staging and KV egress but including the fixed device forward/pipeline work relevant to resume latency.

| `L_hist` | `L_new` | `k` | span cycles | resident-prefix compute | E9 forced estimate | compute ratio | correctness |
|---:|---:|---:|---:|---:|---:|---:|---|
| 7,936 | 256 | 31 | 322,228,241 | **292.935 ms** | 27.206 ms | **10.77×** | cold↔warm byte-identical; warm↔warm identical |
| 7,168 | 1,024 | 28 | 450,599,510 | **409.636 ms** | 107.133 ms | **3.82×** | cold↔warm byte-identical; warm↔warm identical |

The new points agree with the earlier S6a position-weighted chunk-cost model to well under 1%, so the large short-delta floor is reproducible rather than noise. The main correction is qualitative: resident-prefix prefill is not `L_new × 103–156 µs`; for small deltas, fixed per-request work dominates.

### Lane B vs Lane C estimate

For `I_decode(L_hist)`, the two unmeasured 28/31-chunk history points are interpolated from E5's saturated 3.186 GB/s slope: one 256-token KV chunk adds 32 MiB / 3.186 GB/s = 10.532 ms. `F_forced` integrates E9's `71.6 µs + 4.30 ns·position`. E6 supplies delta-only egress under the explicit assumption that a future delta path retains E6's payload cost. `I_decode(L_hist+L_new)` is E5's measured 8,192-token point, 338.266 ms.

| component / total | `L_hist=7936, L_new=256` | `L_hist=7168, L_new=1024` | basis |
|---|---:|---:|---|
| Lane-B history ingress | 327.734 ms | 296.139 ms | E5 saturated-slope interpolation |
| Lane-B forced delta | 27.206 ms | 107.133 ms | E9 fit integral |
| **Lane B total** | **354.940 ms** | **403.271 ms** | estimate |
| Lane-C resident-prefix compute | 292.935 ms | 409.636 ms | **measured WSE-3** |
| Lane-C delta egress | 23.564 ms | 181.791 ms | E6 |
| Lane-C full decode ingress | 338.266 ms | 338.266 ms | E5 measured |
| **Lane C, serial** | **654.765 ms** | **929.693 ms** | estimate |
| **Lane C − Lane B** | **+299.825 ms** | **+526.421 ms** | Lane C loses |
| Lane C, perfect egress/ingress overlap | 631.201 ms | 747.902 ms | optimistic lower bound |
| overlap lower bound − Lane B | +276.261 ms | +344.630 ms | Lane C still loses |

**Result.** The current Lane C is compute-dominated before transport is considered: resident-prefix prefill alone is 10.77× / 3.82× the corresponding forced-decode delta. Adding host-mediated delta egress and decode ingress increases the loss to 300–526 ms. Even perfect overlap of egress and decode ingress does not change the winner.

**Decision implication.** Do not build E12b merely to improve the present design's transport. An exact pdSeparate E12a port remains useful as a final confirmation, because every compared prefill CSL/host file differs bytewise between `e0a19fc` and pdSeparate `6ecb496`; therefore these are a validated screening result, not the final pdSeparate benchmark. But the port would need to remove a 3.8–10.8× compute gap **before** paying transport to reverse the decision. Lane C becomes live only if the design removes most of the per-request prefill floor and likely bypasses/fuses the current host egress plus decode-ingress path.

Evidence:

- Local: `/home/lexu/e12a-sweep-20260802-Sp5ma8/evidence/e12a_delta256.log`
- Local: `/home/lexu/e12a-sweep-20260802-Sp5ma8/evidence/e12a_delta1024.log`
- CS-3 staging: `~/lexu/e12a_sweep_20260802/`
- Jobs: `wsjob-8zy8lthn4hghhrxmgryzda` and `wsjob-bfmuvpzmpu9xdbubpmbcbt`, both completed successfully; no job left running.

## E13 · Decode-side KV egress ✅ — Step 1 DONE (Gate 1/2 + Fig E-1), real WSE-3 (2026-08-03)

The **offload half of lane B** — the eviction cost E10 assumes away — is now **built and measured on real WSE-3**. A decode-side slot's KV can be pulled back to host, byte-correctly. Mechanism: shift-based egress (block east-shift gather → `kv_egress_colmux` NORTH drain → 4-band D2H), `EGRESS_AT_STEP=0` post-ingress dump, config `serve_2x4_8k20k_e13`.

**Gate 1 (shape) + Gate 2 (content) PASS:**
- Egress D2H receives the exact code-derived count with no hang; **decode throughput unchanged (657 µs/tok == E1 baseline)** ⇒ egress ON is non-perturbing.
- **Egressed KV == injected KV bit-for-bit** (k_diff=0, v_diff=0, nonzero=14.68 M). Device emit order == `_repack_kv_band`'s ingress order (layer-outer, per-layer K-all-px then V-all-px, px-inner) ⇒ reload is an identity round trip; correct host inverse = `repack_stream_to_banks`. The first hang was a HOST receive-ordering deadlock (egress fires pre-`main`; host drained it post-logits) — fixed by draining the 4 bands before the logit loop.

**Fig E-1 — decode-side D2H egress cost vs `L_p` (device TSC on the band-0 colmux head):** a **HOCKEY STICK**, mirroring E5.

| `L_p` | plen | payload/band | span_cycles | span_us @0.85 GHz | GB/s band0 (measured) |
|----:|----:|----:|----:|----:|----:|
| 256  | 1  | 8 MiB   | 39,270,494  | 46,200.6  | 0.182 |
| 512  | 2  | 16 MiB  | 39,336,033  | 46,277.7  | 0.363 |
| 1,024 | 4  | 32 MiB  | 47,754,412  | 56,181.7  | 0.597 |
| 2,048 | 8  | 64 MiB  | 72,846,707  | 85,702.0  | 0.783 |
| 4,096 | 16 | 128 MiB | 144,297,198 | 169,761.4 | 0.791 |
| 8,192 | 32 | 256 MiB | 287,114,397 | 337,781.6 | 0.795 |

`span ≈ 46 ms fixed floor + payload / 0.80 GB·s⁻¹·band`. Fixed floor ≈ 46 ms (256 rows serialized NORTH through one head PE; ≈ E5/E2's 46.146 ms) dominates small payloads (256→512 doubles payload, span flat). Marginal ≈ 0.80–0.83 GB/s/band — a striking symmetry with **E5's H2D reload 0.7966 GB/s/band** (same per-band wire rate). `4×` (all bands) ≈ 3.2 GB/s is a **PROJECTION**, not measured (host drains bands sequentially; concurrent aggregate = M4). **Curve complete on all 6 L_p points** (2048/4096 filled 2026-08-04); the saturated marginal 0.80 GB/s/band comes from the 1024→8192 linear region (adjacent marginals 1.14/0.80/0.80 converge; low-L_p marginals are floor artifact). ⚠️ Clock 0.85 GHz (matches the decode-TSC E1 baseline); the 0.85-vs-1.1 GHz reconciliation is open — **raw `span_cycles` preserved** in `decode_device_verdict.json.egress_tsc`.

⇒ **The eviction half of lane B is now priced.** With E5 (reload) + E9 (forced), the offload lane is end-to-end priced at the as-built serialization. **Remaining E13: Gate 3** (decoded-KV round trip) — needs a TOP_K=1 greedy build + the round-trip host-loop restructure; not started.

## E11 · Not yet run

E11 (full re-prefill substitute) can reuse the exact six-point pdSeparate curve above when placed into the fabricated-session comparison. E12b is now gated on an architectural change or an exact pdSeparate E12a result that overturns this negative screening result.

---

# Chapter 3 — Design of the three-lane experiment (E9–E11)

## 3.1 The fabricated session

**Not from a dataset, by decision.** Mooncake's `output_length` is hard-capped at 2,000 tokens (both traces; mean 182–343), so it cannot represent a thinking model's generation. A fabricated session is also the only way to vary each region independently.

```
[system prompt + tool schemas]  [turn 1 ... turn k]      [new context]      [generate]
|---------------- L_hist ----------------------|         |-- L_new --|       |- L_gen -|
        KV assumed already in host DRAM                   not computed        fixed 64
```

**Requirements:** (1) exact token counts per region, verified against the launcher's own tokenizer+chat template; (2) coherent, not word salad (E8 showed noise makes the model loop); (3) non-repeating across regions; (4) region boundaries on chunk multiples (256); (5) ⚠️ pin the tokenizer revision (`70d244cc`), chat template, and tool-schema text, and persist rendered token IDs per region — analysis reads persisted IDs, never re-tokenizes.

## 3.2 Parameter grid

| parameter | values | why |
|-----------|--------|-----|
| `L_hist` | 0, 512, 1024, 2048, 4096, 8192 | the main sweep — spans E5's floor, knee, linear region. 0 is the control (B→A) |
| `L_new` | 256, 1024, 4096 | the delta the lanes disagree about |
| `L_gen` | 64, fixed | keeps generation from confounding |

Constraints: `L_hist + L_new + L_gen ≤ 20,480` (decode ceiling); for E11 only, `L_hist + L_new ≤ 8,192` (prefill `MAX_INPUT_LEN`).

## 3.3 The ingress payload, stated in bytes

```
band_bytes = 8 MiB × ceil(L/256) + 1 MiB          (the 1 MiB constant tracks KV_META_LEN = 4)
total      = 4 × band_bytes = 32 MiB × ceil(L/256) + 4 MiB
```

`ceil` matters: a partial chunk loads as a whole chunk. The grid lands every `L_hist` on a chunk multiple E5 already measured — lane B's reload cost is **measured, not modelled**:

| `L_hist` | chunks | ingress (E5, measured) |
|----------|--------|------------------------|
| 512 | 2 | 46.236 ms |
| 1,024 | 4 | 56.141 ms |
| 2,048 | 8 | 85.684 ms |
| 4,096 | 16 | 169.891 ms |
| 8,192 | 32 | 338.266 ms |

⚠️ Assumes lane B's injection uses the same per-round path E5 timed. `kv_ingress_span_us` is reported per round, so E10 **verifies** rather than assumes.

## 3.4 Pre-recorded predictions

⚠️ The E10 prediction rested on an intercept back-solved from E3's single point; E9 has now replaced it with a measured fit. **E9 measured β=4.30 ns/tok**, so the "E9-slope quadratic" envelope below (which assumed β=28.3) is **refuted** — lane A ≈ E3-constant × F to the ceiling (measured 735 ms at F=8192 vs the constant's 723.8).

| `L_hist` | lane A, E3-constant (88.35 µs) | lane A, MEASURED (E9) | lane B (measured) |
|----------|-------------------------------|-----------------------|-------------------|
| 512 | 45.2 ms | 37.9 ms | **46.24 ms** |
| 1,024 | 90.5 ms | 76.9 ms | **56.14 ms** |
| 2,048 | 180.9 ms | 158.3 ms | **85.68 ms** |
| 4,096 | 361.9 ms | 333.5 ms | **169.89 ms** |
| 8,192 | 723.8 ms | 735.1 ms | **338.27 ms** |

⇒ crossing predicted at `L_hist ≈ 520–900`: below it, force-decoding the whole thing (A) is cheaper than paying the ~46 ms reload floor (B); above it, B wins and pulls away (A grows ~linearly at ~74–98 µs/tok while B grows at E5's saturated 3.186 GB/s aggregate). **Falsifier:** a crossing outside 400–1,500 kills the model.

⚠️ **The `L_new` cancellation is a HYPOTHESIS, not an identity.** Both lanes are charged `Σ f_forced` over `L_new`, but that only cancels if lane B's forced decode starts from a state equivalent to lane A's (same KV layout, no extra warm-up / queue drain / first-token penalty from the ingress). **E10 measures the segments separately:** `lane B total − kv_ingress_span_us = post-ingress forced segment`; `lane A total = full-rebuild forced segment`. If the per-token cost of `L_new` differs between lanes, that difference is the finding.

**E11 — the full re-prefill baseline.** Prefill's amortised per-token cost was ~103–156 µs across E4–E7's bins. Prediction: it loses to lane B at every `L_hist ≥ 1,024`, paying a prefill floor *and* a full-payload ingress. ⚠️ A **substitute**, not a strict bound: if it loses, true lane C may still win; if it wins, lane C is worth building (E12). Only the second direction is conclusive.

## 3.5 What each experiment plots

| ID | figure | x | y | series | what a reader should see |
|----|--------|---|---|--------|--------------------------|
| E9 | forced-token cost | force-decode position | µs/tok and tok/s | forced (points+fit) + free (E7) | forced ≈ 0.12× free, NOT parallel — **done, see chart above** |
| E10 | the resume-latency boundary | `L_hist` | resume latency (ms), log y | lane A, lane B; one panel per `L_new` | two lines crossing once, B pulling away |
| E10b | decomposition | `L_hist` | stacked ms | ingress / forced-decode / fixed | which term owns the cost in each regime |
| E11 | full re-prefill baseline | `L_hist + L_new` | resume latency (ms) | A, B, C0 | whether C0 is ever below the other two |

## 3.6 Build status and honesty about scope

| lane | measurable today? | what is missing |
|------|-------------------|-----------------|
| A | ✅ | nothing — E3's mechanism with large `F` (now measured, E9) |
| B | ✅ resume only | the eviction half (decode→host) is E13, unbuilt. E10 assumes DRAM already holds `L_hist` |
| C | ⚠️ compute screened negative | resident-prefix compute measured through the validated S6a path; exact pdSeparate port and prefill KV ingress remain unbuilt. Current host-mediated design is not competitive |

**E10's result will be a statement about resume latency in a session whose history is already persisted — not a full offload-vs-recompute verdict.** Stating this in the figure caption is part of the deliverable.

**Known confound: history provenance.** `L_hist` is assumed resident — fabricated and injected, never actually produced by an earlier decode turn. Doesn't affect the resume-latency measurement (same bytes, same path), but E10 cannot see whether decode-produced and host-reloaded KV stay equivalent over a long history. Testable later with an equivalence control that needs E13.

---

## Change log

* **2026-07-31** — register created. E6's "asymmetry reversed / 5.10×" retracted (prefill egress carries a transpose+gather; not comparable to decode ingress). A7's falsification withdrawn (Mooncake `output_length` capped at 2,000). Scenario fixed to the three-lane resume race; E9–E13 defined. Design reviewed by Codex — 8 findings applied.
* **2026-07-31 (later)** — **E9 done and filed** (recovered from the lost `m2-s3-0` session; raw `timing.json` re-analysed, bit-reproduced). Forced decode has its own `f(pos) = 71.6 µs + 4.30 ns·pos`; forced ≈ 0.12 × free; the `F=1` control exposed a ~22 ms startup contamination at `P=256` (initially called pipeline fill; superseded by the E14 method correction below). Mechanism: 8 (2×4) block pipeline, ratio ≈ `max_lpb/n_layers = 4/28`, not 1/N_blocks. Chart added. **Correction:** an interim writeup called lane A "quadratic" with a "~30 ns/tok slope" — **both wrong**; the measured slope is 4.30 ns/tok and lane A is linear-dominated to the ceiling (≈ E3-constant × F to ~1.6% at 8192). ROADMAP and this register corrected. **E10 next; no new code.**
* **2026-08-02** — **E14 measured on real WSE-3 (n=1, TSC 0.85 GHz).** The F=1 startup anchor grows with prefix, while all F_lo≥256 marginal segments collapse onto `71.745198 µs + 4.093307 ns×position` (R²=0.997447). The ~700-token E10 crossing is therefore one slice of a boundary surface parameterized by starting prefix, reload policy, and `L_new`. Two repeat attempts hit ingress 502 and were not counted without a hash-verified evidence bundle.
* **2026-08-02 (E12a screening)** — **Resident-prefix incremental prefill measured on real WSE-3 using isolated S6a commit `e0a19fc`.** At total context 8,192, `L_new=256` took 292.935 ms (`L_hist=7,936`, 10.77× the E9 forced estimate) and `L_new=1,024` took 409.636 ms (`L_hist=7,168`, 3.82× forced); both cold↔warm and warm↔warm KV checks were byte-identical. With E5/E6 transport, serial Lane C is estimated at 654.765 / 929.693 ms vs Lane B 354.940 / 403.271 ms; even perfect egress/ingress overlap leaves Lane C +276 / +345 ms slower. This is a validated negative screening result, not the exact pdSeparate benchmark: `6ecb496` lacks `START_CHUNKS` and its prefill files differ bytewise. Decision: do not build E12b for the current host-mediated design unless an exact pdSeparate port overturns the 3.8–10.8× compute gap.
* **2026-08-02 (E14 method correction)** — Replaced the misleading “fixed pipeline-fill offset” interpretation with `ready + fill + steady + tail`. Source timing shows the `[N,F]` header is not a global readiness barrier; inferred `T_ready` grows from 21.406 ms at `P=256` to 223.355 ms at `P=8192`, while estimated fill remains 0.510–0.737 ms and tail ≈0.12 ms. Documented the 16-point adjacent-segment regression that produces `a=71.745198 µs` and `b=4.093307 ns/position`; retained `D(P,256)` as the robust startup anchor pending a first-Z timestamp.

* **2026-08-03 (E13 Step 1)** — **Decode-side KV egress BUILT + measured on real WSE-3.** Gate 1 (shape) + Gate 2 (content) PASS: egressed KV == injected KV bit-for-bit (k_diff=0/v_diff=0), decode throughput unchanged (657 µs/tok). **Fig E-1** (decode-side D2H cost, device TSC on the band-0 colmux head) is a hockey stick: `span ≈ 46 ms floor + payload / 0.80 GB·s⁻¹·band`; marginal 0.80–0.83 GB/s/band ≈ E5's H2D reload 0.7966/band; floor ≈ 46 ms ≈ E5/E2. 4 clean L_p points (256/512/1024/8192); 2048/4096 = ingress-502 casualties. `4×`≈3.2 GB/s is a projection (concurrent = M4). Clock 0.85 GHz (raw span_cycles preserved; 1.1 GHz reconciliation open). ⇒ **the eviction half of lane B is now priced.** Every change: implement → Codex-APPROVE → gate; nothing committed. Remaining E13 = Gate 3 (decoded-KV round trip). Detail: work-repo `models/qwen3_1p7b-e2e-pdSeparate/E13_SESSION_LOG.md`.
* **2026-08-04 (Fig E-1 curve complete + Gate 3 started)** — Filled L_p 2048/4096 (0.783 / 0.791 GB/s band0); the hockey stick stands on all 6 points, marginal converges to 0.80 GB/s/band (1024→8192). Gate 3 design fully Codex-vetted (2 rounds) + CSL crux implemented (`decode.csl:1937 egress_plen = iter_num_bank[0]`, inert) + Codex-reviewed [ok] with one launch-guard blocker (L,L+K ≤ MAX_SEQ_LEN−P). Remaining = the host round-trip loop + a TOP_K=1 greedy build. Design: work-repo E13_GATE3_DESIGN.md.
* **2026-08-03 (Lane B definition — full-KV reload has no forced delta)** — Drained from `memory/inbox/2026-08-03-lane-b-full-kv-reload-has-no-forced-delta.md` (author human). When the three-lane resume study defines Lane B as loading the **complete target-position KV snapshot** from host DRAM (the full-reload policy, `B_full` in E14 Result 3), its resume-to-KV-ready cost is **`B(L) = I(L)` with zero on-card reconstruction compute** — adding a post-ingress forced-decode term **double-counts**. The next normal free-decode token is a **common tail**: exclude it from all lanes or add it to all lanes; never charge it only to Lane B. For the two slide-12 cases whose final context is 8,192, Lane B is therefore `I(8192) = 338.266 ms` in both. E10/E10D's older `reload history + force-decode L_new` fixture remains valid evidence for the **delta-reload** policy (`B_delta`) but must not be presented as the current full-KV Lane B definition. **Follow-up (see plan.md):** audit the Lane B equation and the A/B-crossing slides for the same delta-reload vs full-KV-reload definition mismatch (`meetings/2026-08-02.pptx` slide 12, `meetings/2026-08-02-src/make_figures.py`).
