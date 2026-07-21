# Prefill prefix-reuse — real-scale device measurement (524k PEs, Qwen3-1.7B dims)

Date: 2026-07-19 · Repo: `WaferEngine-staging` · Branch: `lexu/staging/s6a-inner-pe-kv-route-a` (uncommitted)
Status: drained 2026-07-20 into `plan.md`, `memory/topics/s6a-prefill-warm-start.md`, `memory/context.md`, and `tracking/status.md`.
Companion capture: `2026-07-19-s6a-prefill-warm-start-bringup.md` (the three defects + bring-up).

First **real-scale** measurement of prefill-side prefix reuse (`START_CHUNKS` warm-start). Supersedes
the mock-scale numbers in the companion capture — those were 256–512 PEs / dim=64 and are only
directional.

## Setup

| | |
|---|---|
| config | `models/qwen3_1p7b-prefill/model_config/test_device_real_L8192_k{0,8,16,24}.json` |
| base | `test_device_2x4_kv_varlen.json` (shipped real config) |
| geometry | Pw=512 × Ph=1024 = **524,288 PEs**, 2×4 blocks, `P_BLOCK_SIZE = 256` |
| model dims | dim=2048, head_dim=128, 16 heads / 8 kv-heads, ffn 6144, **28 layers**, vocab **151,936** |
| sequence | `PREFILL_LEN = MAX_SEQ_LEN = 8192`, `CHUNK_SIZE = 256` → **32 chunks** |
| workload | 3 requests, `PREFILL_LENS = [8192, 8192, 8192]`, `START_CHUNKS = [0, k, k]` |
| device | real WSE-3 via CS-3; compile ≈ 419 s, run ≈ 14–15 s wall |
| n | **1 run per point** (no repeats — variance not characterised) |

The grid differs **only** in `START_CHUNKS`; the compiled artifact shape is identical across points.

## Raw numbers

| k | reuse | span_cycles | forward time | throughput (harness) | host wall |
|---:|---:|---:|---:|---:|---:|
| 0 | 0 % | 1,101,615,635 | 1001.47 ms | 8,180.0 tok/s | 15.2 s |
| 8 | 25 % | 1,016,462,831 | 924.06 ms | 8,865.3 tok/s | 14.9 s |
| 16 | 50 % | 850,635,411 | 773.30 ms | 10,593.5 tok/s | 14.5 s |
| 24 | 75 % | 604,117,559 | 549.20 ms | 14,916.3 tok/s | 13.8 s |

**What the span actually measures — verified in `ht_tail.csl`.** `is_tsc_pe` parks on the kickoff
sentinel from demux PE 0 and samples **start when the first tokens land on device** (the comment is
explicit: "the FORWARD start, *not* device-start"); it samples **end after the logits blob emit**.
The serve loop receives one 8-u32 `tsc_burst` **per request**, overwriting the variable each round,
so the reported span is the **last request's** forward.

That makes this metric exactly **pure single-request device latency**: host-side stream preparation
and result post-processing are both outside the window. In this grid the last request carries
`start_chunk = k`, so the span measures the *warm* request. Throughput (`PREFILL_LEN / span`) is
therefore a correct **per-request** figure:

| k | per-request latency | per-request throughput | vs k=0 |
|---:|---:|---:|---:|
| 0 | 1001.47 ms | 8,180.0 tok/s | — |
| 8 | 924.06 ms | 8,865.3 tok/s | +8.4 % |
| 16 | 773.30 ms | 10,593.5 tok/s | +29.5 % |
| 24 | 549.20 ms | 14,916.3 tok/s | **+82.3 %** |

*(An earlier draft of this capture divided 3 × 8192 tokens by the span to derive an "aggregate"
throughput. That was wrong — the span covers one request, not three. The table above supersedes it.
The saving percentages and the +82.3 % gain are ratios and are unaffected.)*

**Host wall-clock is NOT a valid latency metric here** and is reported only as run context: it
includes weight loading, per-request stream construction, and logit post-processing on the host.

Reference point — the shipped varlen config (`test_device_2x4_kv_varlen`, 4 requests,
lens `[8192, 4096, 8192, 4096]`, no reuse): span 407,010,641 cycles, 370.0 ms, 22,140 tok/s
(harness semantics), run 14.4 s, `BYTE-IDENTICAL PASS`.

## Derived — saving vs reuse fraction

| reuse k/n | measured saving | (k/n)² | delta |
|---:|---:|---:|---:|
| 25 % | **7.7 %** | 6.2 % | +1.5 % |
| 50 % | **22.8 %** | 25.0 % | −2.2 % |
| 75 % | **45.2 %** | 56.2 % | −11.1 % |

`(k/n)²` (from the mock-scale capture) is a **rough** approximation only. The real curve sits between
linear and quadratic and falls increasingly short of the quadratic at high reuse — a per-request
fixed overhead that no amount of chunk-skipping removes puts a floor under the span.

## Derived — marginal cost per chunk (the useful form)

| chunks skipped | mean position | saving | **per chunk** |
|---|---:|---:|---:|
| 0–7 | 3.5 | 85.2 M | **10.64 M cycles** |
| 8–15 | 11.5 | 165.8 M | **20.73 M cycles** |
| 16–23 | 19.5 | 246.5 M | **30.81 M cycles** |

Fitting `cost(chunk c) = a + b·c`:

```
a ≈ 6.2 M cycles    (per-chunk fixed: its own QKV / FFN / norm work)
b ≈ 1.26 M cycles   (per preceding chunk: attention over the accumulated prefix)
```

So the **last** chunk (c=31) costs ≈ 45 M — about **7× the first**. This is the mechanism behind the
diminishing returns: **a reused prefix is made of the cheapest chunks in the request; the recomputed
suffix is the expensive part.**

## Correctness

Every point: `KV round 1 vs round 0` and `round 2 vs round 0` both **BYTE-IDENTICAL PASS**, tokens
`all-equal=True`. So at 8192 tokens / 32 chunks / real dims, warm-start reproduces the cold result
exactly while measurably reducing work — reuse is provably *engaging* (the span moves monotonically
with k) and provably *correct*.

## Decision-relevant reading

**Prefill-side prefix reuse is strongly sub-linear in the hit fraction.** 50 % prefix reuse buys
~23 % of the time; you need ~75 % before the saving approaches half. Consequences:

- **M1 (skip-prefill-on-hit):** benefit scales far worse than the hit *rate* suggests. A prefix cache
  that mostly yields short prefixes will underdeliver relative to a naive linear estimate.
- **M2 (`R*` breakeven):** the numerator — time saved by reuse — is **not** a function of reused
  *length* alone; it depends on **where in the sequence** the reused span sits. The current
  `R* = Δ·BW/B_tok` formulation has no term for that. Position-weighting is needed.

## Caveats

- **n = 1 per point.** No repeat runs; run-to-run variance uncharacterised. The monotone trend across
  four points and the clean linear fit of the marginal cost argue against noise dominating, but this
  is not a distribution.
- Single sequence length (8192) — the length axis was not swept at real scale.
- Only the **prefill** side. Decode-side reuse is **not** measured (see below).

## Decode — SUPERSEDED, see the ADDENDUM at the end of this file

> **This section is wrong and is kept only as a record of the wrong turn.** It concluded decode's
> reuse benefit was unmeasurable and proposed adding a prefill-phase timer to decode. Both claims are
> retracted: decode never computes prefill, its existing TSC already excludes KV loading and is the
> correct metric, and once the comparison was designed properly the benefit measured **−34.6 %** of
> total decode work. See **ADDENDUM — decode DOES save compute** below.

What it said at the time: the retain path engages (rounds 1,2 show `prefill=0`) but showed no span
difference; a first grid was also mis-designed (with `MAX_SEQ_LEN` fixed, `max_output_len =
MAX_SEQ_LEN − PREFILL_LEN`, so sweeping prefix length traded prefill work for decode steps and the
baseline came out flat at 26.9 / 27.4 / 26.8 s).

---

## ADDENDUM (same day, later) — decode DOES save compute; earlier conclusion retracted

### Retraction

An earlier revision of this capture concluded "decode has no independent reuse benefit; the saving
lives entirely in prefill." **That was wrong**, and it was wrong because the comparison was designed
badly, not because the implementation lacks a benefit.

The failed comparisons held **decode step count equal in both arms** (base re-injected the prefix and
decoded D steps; reuse retained it and decoded D steps). With identical work, identical spans — of
course. Two such grids were run before the flaw was spotted; a third, where both arms ended at the
same 2L context with the same 256 decode steps, likewise showed only 1.1 % difference, confirming
that reuse per se does not change decode compute.

**The null result, in full.** This is the **abandoned first design**, kept as a record of what it
does and does not show. Real scale, `MAX_SEQ_LEN = 1024`; the reported span is the **last round**
(decode's TSC variable is overwritten each round):

```
base  : PREFILL_LENS=[L,L,L]  DECODE_LENS=[256,256,256]  RETAIN=[0,0,0]
        -> every round is an independent request: fresh prefill L, then decode 256
reuse : PREFILL_LENS=[L,0,0]  DECODE_LENS=[256,256,256]  RETAIN=[0,1,1]  RETAINED=[L,L,L]
        -> round 0 prefills L; rounds 1-2 inherit it, then decode 256
```

Both arms therefore run **256 decode steps over the same peak context** in the measured round —
equal work by construction:

| prefix L | peak ctx | base span | reuse span | delta |
|---:|---:|---:|---:|---:|
| 256 | 512 | 126,179,797 | 126,209,250 | **+0.023 %** |
| 512 | 768 | 127,668,458 | 127,698,287 | **+0.023 %** |
| 768 | 1024 | 129,022,259 | 129,050,658 | **+0.022 %** |

All six rc=0. Reuse is *very slightly slower* — a constant \~29 K cycles, independent of L, i.e. the
fixed cost of the retain bookkeeping itself, not a per-token effect.

**Read this narrowly.** It says: when both arms run the same number of decode steps over the same
context, retain changes decode compute by \~0.02 % — i.e. **a retained step is not a cheaper step**.

**It does NOT say retain is worthless here, and the design has a second flaw worth naming.** The only
thing that differs between the arms is *whether this round re-prefilled the prefix or inherited it* —
and that difference falls **outside the measurement window**, because decode's TSC starts at
`tail_step == warmup_cycles`, i.e. after KV injection. The base arm really does pay a fresh prefill
every round; this metric simply cannot see it. So the grid is blind twice over: equal decode work by
construction, and the one real difference excluded by the timer.

Retain's benefit is **not executing steps at all**, which is why the comparison was redesigned so the
no-reuse arm redoes the steps it discarded (next section). Kept because anyone re-running this will
likely build the equal-work grid first — these numbers show what that looks like and why it settles
nothing.

Also note the span grows with context even at fixed step count (126.2 M → 129.0 M as peak ctx goes
512 → 1024, +2.3 %), which is the decode-side echo of the prefill position effect.

### The correct comparison — and the real benefit

The benefit of decode retain is **not re-executing decode steps that already ran**. Both arms must
reach the *same end state*; the no-reuse arm must therefore redo the discarded work:

```
end state: prefill L, then 2D tokens decoded

no-reuse : round 0 decodes D;  round 1 discards KV -> must redo D + new D = 2D steps   total 3D
reuse    : round 0 decodes D;  round 1 inherits KV -> only the new D steps             total 2D
```

Measured at real scale (524,288 PEs, `MAX_SEQ_LEN = 1024`, L = D = 256):

| | round 0 | round 1 | total decode |
|---|---:|---:|---:|
| no-reuse (`DECODE_LENS=[256,512]`, `RETAIN=[0,0]`) | 127.7 M | **262,928,666** | 390.6 M |
| reuse (`DECODE_LENS=[256,256]`, `RETAIN=[0,1]`, `RETAINED=[0,-1]`) | 127.7 M | **127,696,962** | 255.4 M |
| | | **−51.4 %** (2.059×) | **−34.6 %** |

Matches the step-count prediction (768 → 512 steps = −33 %). Per-step cost: 513.5 K (no-reuse)
vs 498.8 K (reuse) cycles — the 2.9 % gap is the no-reuse arm attending over a longer accumulated
context in its later steps.

**This span is a clean compute measurement.** Decode's TSC starts at `tail_step == warmup_cycles`,
i.e. *after* KV injection, so KV loading is already outside the window — no harness change needed.
(An earlier note in this capture proposed adding a prefill-phase timer to decode. Retracted: decode
never computes prefill, and the metric it needs was already correct.)

Note the host→device KV volume also drops (314.6 MB → 113.2 MB, −64 %, retain rounds degrade to a
meta-only heartbeat), but that is an artifact of the standalone harness — in a served pipeline the
retained KV is already on-chip and never crosses the host bus. **Not a serving benefit; do not quote it.**

### Decode at a SECOND length — MAX_SEQ_LEN = 4096 (measured 2026-07-21)

The `MAX_SEQ_LEN = 1024` result above had no length companion — decode's length axis was empty. Now
filled, at `MAX_SEQ_LEN = 4096`, D = 1024 decode steps per round (same two-round redo design: no-reuse
redoes the discarded round, reuse inherits it):

| arm | span_cycles | rounds |
|---|---:|---|
| no-reuse (`d2_noreuse`, `DECODE_LENS=[1024,2048]`, `RETAIN=[0,0]`) | 1,120,316,570 | round0 decodes 1024; round1 redoes 1024 + 1024 new = 2048 |
| reuse (`d2_reuse`, `DECODE_LENS=[1024,1024]`, `RETAIN=[0,1]`, `RETAINED=[0,-1]`) | 567,975,120 | round0 decodes 1024; round1 inherits, only the 1024 new |
| | **−49.3 %** (1.972×) | |

Both rc=0. **Decode reuse saving is essentially length-invariant on the total-work metric**: the
1024-context version saved −34.6 % of total decode, but that grid decoded 3D vs 2D total (a 1/3
reduction ceiling); this 4096 grid is the cleaner two-round shape where reuse elides one whole
discarded round (2048→1024 of the second round's steps), so it lands near the −50 % structural
ceiling. Read the two together as: **the saving equals the fraction of decode steps that do not have
to be re-executed**, which is a property of the redo pattern, not the sequence length — consistent
with the prefill-side finding that reuse payoff tracks the reuse *fraction*. The per-round step count
scales with `MAX_SEQ_LEN`, so the *absolute* cycles grow (567.9 M vs 127.7 M) but the *ratio* is set
by the workload design, not the length.

## Sequence-length scaling — partial (cluster dropped mid-batch)

Capacity probes at real scale (`--compile-only` on device):

| kernel | compiles | fails at | cause |
|---|---|---|---|
| prefill | **16384** (64 chunks) | 32768 | `integer value 33020 cannot be coerced to type 'i16'` — an **i16 overflow**, not memory |
| decode | **4096** (kv_len_per_pe = 16) | not reached | i8 stride bound is `127 × P_BLOCK_SIZE` = 32,512 at real scale — not binding |

*(Correction to an earlier capture: the "decode caps at MAX_SEQ_LEN ≤ 1016" note was derived on the
mock `P_BLOCK_SIZE = 8`. The bound scales with `P_BLOCK_SIZE`; at real scale it is not a constraint.)*

Only the k=0 point of the L=16384 sweep completed before the CS-3 gateway connection dropped
(`Connection closed by UNKNOWN port 65535`; the remaining 5 runs failed instantly with rc=255,
no jobs left holding a wafer). That single point is still informative:

| | L = 8192 | L = 16384 | ratio |
|---|---:|---:|---:|
| single-request device latency (cold) | 1001.47 ms | **3144.94 ms** | **×3.14** |
| throughput | 8,180 tok/s | 5,209.6 tok/s | −36 % |

**Doubling the sequence more than triples the time** — between linear (2×) and quadratic (4×), which
directly confirms that per-token cost grows with sequence length. The `cost = n·a + b·n²/2` fit from
L=8192 predicts 3.57×; measured 3.14×, so the model's position slope is somewhat too steep at 2× the
length but right in direction and magnitude.

### The L=16384 reuse sweep — COMPLETE 2026-07-21 (k48 filled in), prediction still falsified but the "same curve" claim is narrowed

Chart: `assets/s6a-prefix-reuse/prefill-prefix-reuse-latency-throughput.svg` (+ `.png`), generated by
`assets/s6a-prefix-reuse/_gen_chart.py`.

| k | reuse | span_cycles | latency | throughput | saving vs k=0 |
|---:|---:|---:|---:|---:|---:|
| 0 | 0 % | 3,459,432,815 | 3144.94 ms | 5,209.6 tok/s | — |
| 16 | 25 % | 3,208,533,364 | 2916.85 ms | 5,617.0 tok/s | **7.25 %** |
| 32 | 50 % | 2,634,720,942 | 2395.20 ms | 6,840.3 tok/s | **23.84 %** |
| 48 | 75 % | **1,738,254,665** | **1580.23 ms** | **10,368.1 tok/s** | **49.75 %** |

All four points `BYTE-IDENTICAL PASS`, tokens `all-equal=True`. (k48 measured 2026-07-21 after the
gateway recovered; it had been the sole gap.)

**The original prediction was wrong in direction** — it said saving at L=16384 should be *lower* than
at L=8192, and it is not. But with k48 in hand the earlier "the two lengths lie on the same curve"
claim is **too strong**. Full comparison:

| reuse fraction | L = 8192 | L = 16384 | delta |
|---:|---:|---:|---:|
| 25 % | 7.73 % | 7.25 % | −0.48 |
| 50 % | 22.78 % | 23.84 % | **+1.06** |
| 75 % | 45.16 % | **49.75 %** | **+4.59** |

At low reuse the two lengths are within noise, but by 75 % the longer prompt saves **4.6 points
more** — and the gap *grows monotonically* with reuse fraction (−0.5 → +1.1 → +4.6). So the honest
statement is: **saving is dominated by the reuse fraction, with a second-order length dependence that
only becomes visible at high reuse, and there favours the longer prompt.** The mechanism is the one
the earlier note half-had: at high reuse the skipped prefix is disproportionately the expensive
late-position chunks, and those grow with `n` (the `b·c` term), so a longer prompt has *more* to gain
from skipping the same *fraction*. The `(k/n)²` toy captures the sign of this; the linear-fraction
model does not.

**Consequence for M1/M2:** reuse *fraction* is still the right primary variable, but a cost model that
drops length entirely will **under-predict the payoff of high-reuse hits on long prompts**. If a
single variable is wanted, fraction is defensible up to ~50 % reuse; past that, a length term earns
its place. Still n = 1 per point — the monotone, clean trend argues against noise, but it is not a
distribution.

**Now closed:** `p2_L16384_k48` (above). The decode length axis is also measured — see the decode
section's L=4096 addendum below. Every set#2 point is done; nothing is left staged.

## Operational — how a device result survives, and how it does not

**`out_*` artifact dirs never come back from a device run.** `launch_device.py` drives `SdkLauncher`,
which ships the staged tree to a *worker* node and runs there; the login node keeps only
`device_staging_<cfg>/` (the inputs). Checking `~/rsync/.../models/*/out_*` on the login node the day
after returns `No such file or directory` — **this is normal, not data loss.**

Consequence: **the captured stdout IS the result.** If a batch's output is not redirected to a file
that outlives the ssh session, the measurement is gone and the only recovery is a re-run costing a
full compile (\~420 s at L=16384). Every device batch must tee per-point logs to local disk. All
numbers in this capture survive only because they were captured that way.

Related failure mode worth one line: in a *local* driver script, a `~` in a path destined for the
remote shell must stay **literal** — an unquoted `~` expands locally (`/home/lexu`) and the remote
`cd` fails in ~2 s with `No such file or directory`. It looks like a cluster/connection fault and is
not one. Read the per-point log before concluding the cluster dropped.
