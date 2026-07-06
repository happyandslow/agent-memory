# KV-Cache Preserve-vs-Evict Policy Tradeoffs (WSE-3)

## Summary

Central research question (Le, 2026-07-05): for a single request, compare the cost
of **preserving** its KV cache (so future requests reuse it and save prefill
compute) vs **evicting** it (free the resource now; a later request recomputes the
KV). The two qwen3_1p7b end-to-end deployments sit at **opposite ends** of this
tradeoff and are the platform for exploring it:

- **`models/qwen3_1p7b-e2e`** (prefill+decode co-resident, **on-chip KV relay**):
  KV lives only in decode-side SRAM. Reuse would be transfer-free, but capacity is
  a single overwritten cache slab (no host-visible copy, no multi-request
  addressing). This is the *no-offload* corner.
- **`models/qwen3_1p7b-e2e-pdSeparate`** (PD-disaggregation, **KV bridges through
  host DRAM** as `inj_xk/inj_xv` npz): the host already holds the full KV off-chip,
  so a large retained pool + real eviction policy (LRU/priority) is buildable. This
  is the *tiered/offload* corner.

**Neither deployment reuses KV across requests today.** The *standalone* decode
has multi-round machinery (`round_reset` rewinds `iter_num` and overwrites the
slabs each round — reuse of the slabs, not of the content). But the **integrated
e2e/pdSeparate are even more limited: they have NO multi-round support at all**
(single request per compiled load — see [[standalone-vs-integrated-kernel-parity]]).
Exploring any preserve policy means *adding* a keyed KV store + a "skip prefill on
hit" decision — and, for the integrated homes, first re-absorbing the standalone's
varlen multi-round KV ingress.

## The tiering design space (preserve has more than 2 options)

Preserving KV is not binary (on-chip vs evict) — there is a **cost-ordered tier
ladder**, and the right choice is a per-request cost decision:

| Tier | Where KV is parked | Reuse (reload) cost | Capacity | Notes |
|---|---|---|---|---|
| T0 in-place resident | decode PE's own SRAM | ~0 (never moves) | tiny — one cache, ≤ MAX_SEQ_LEN | occupies the working slab; blocks new request |
| **T0.5 in-bank / in-PE multi-request reuse** | the SAME compute bank, holding >1 request's KV | **~0 — reused in place, never moves** | on-chip SRAM shared across cached requests (tightest — competes with the active request for the bank) | **(Le's addition)** cheapest reuse of all (no move), but needs KERNEL support: multi-request bank partition/keying + `round_reset` retain+extend instead of rewind. Home discussable: **decode** (where warm KV sits) or **prefill** — different tradeoffs (see "Where reuse is computed"). |
| **T1 idle-PE SRAM offload** | spare/empty PEs on the *same wafer* | on-fabric gather (router hops, ns–µs, no host BW) | (#free PEs × ~48 KB) — wafer-scale spatial abundance | **wafer-unique middle tier** (Le's idea); needs a park-band + addressing. Difference vs T0.5: T0.5 reuses *inside* the compute bank (no move, competes for bank space); T1 *moves* to separate idle PEs (frees the bank, pays a move). |
| T2 host-DRAM offload | host memory (pdSeparate egress path) | ingress stream ~29 MB/req, "a few s" | large (DRAM) | already implemented one-way (prefill→decode) |
| T3 evict + recompute | nowhere | rerun prefill (~5.7 s @256 tok; **capped ≤~512-tok prompt**, see below) | n/a | pays prefill FLOPs on miss |

**The decision depends on cost** (Le's framing): storage bytes (T0/T1 scarce ~48
KB/PE vs T2 abundant), movement-per-reuse (T0≈0 < T1 fabric < T2 host-I/O < T3
recompute), and opportunity cost (T0/T1 occupy wafer resources that could serve
other requests; T2 frees the wafer entirely). **T1 (idle-PE offload) is the
interesting wafer-scale-native option** — park KV in otherwise-idle PEs at fabric
speed, far cheaper than a host round-trip and far higher capacity than in-place —
but its real cost (fabric BW for the move, addressing/relayout, how many PEs are
actually free) is unquantified. e2e already uses 645×1028 of the 762×1176 fabric,
so *some* PEs are free but not a huge reserve at this config.

## Multi-request (standalone) = ISOLATION, not reuse — but the reload transport is already there

Important clarification on the standalone `NUM_ROUNDS` multi-request mode (verified
in code 2026-07-05): serving multiple requests from one loaded artifact does **not**
reuse KV across them today — it deliberately *isolates* them.

- **Serve loop** (`decode/launch.py:2489` `for rnd in range(num_rounds)`): each round
  the host streams a **fresh KV prefix** (`inj_xk/inj_xv`) + `X[0]` seed into
  `kv_ingress`, decodes, drains logits, then sends the next round. Between rounds the
  device **re-arms** (no stop/relaunch).
- **`round_reset()`** (`decode.csl:265-281`) at each round rewinds `iter_num` to the
  new prefill length, zeroes `step`, re-seeds RoPE from (1,0), recomputes the decode
  budget → **the prior round's KV is discarded/overwritten**.
- The host **re-arm validation** (`launch.py:2540-2549`) asserts two same-prefill
  rounds are **bit-identical** — its explicit purpose is to prove **no cross-round
  state carryover**. That is the *opposite* of reuse (it guarantees statelessness).

So single→multi-request changes **nothing** about KV reuse: each request is isolated,
KV re-injected fresh and discarded per round. What multi-request reuses is the
compiled artifact, resident (compile-baked) weights, and SRAM slabs *as storage* —
never KV content. Prefill side is symmetric: each round prefills a new prompt
(`PREFILL_LENS`) from scratch and egresses fresh KV with a `round_sync` re-arm barrier.

**The actionable upside:** the per-round host→decode KV injection **IS the T2
"reload from host DRAM" transport** already implemented. Today it always streams a
fresh prefill's KV; reuse = stream a *retained prior request's* KV on a cache hit and
skip prefill. So the gap from "multi-request" to "prefix-caching / KV reuse" is
**only a policy layer**, not plumbing: (1) a keyed host-DRAM store of prior
`inj_xk/inj_xv` (retain instead of discard), (2) a cache-hit decision to skip prefill
and inject the retained KV, (3) make `round_reset` conditionally **retain + extend** a
prior KV instead of always rewinding. The integrated e2e/pdSeparate have **no
multi-round loop at all**, so they lack even this reload transport
([[standalone-vs-integrated-kernel-parity]]).

## Multi-turn append — the ship-back-to-prefill subtlety

For multi-turn conversations the reusable KV for `[P1,R1]` includes **R1's KV,
produced by the DECODE kernel** (in decode's XKCache/XVCache layout). To extend
with a new user turn P2:

- **(a) Continue in decode (force-decode P2):** decode already holds the KV, does
  causal attention + appends per step → **no ship-back, transfer-free**, but
  **serial** over P2 (loses parallel prefill).
- **(b) Prefill P2 in parallel:** prefill's attention for P2 needs the prior
  `[P1,R1]` KV at every layer (P2's hidden states, hence its K/V, depend on it from
  layer 1 on) → **you must ship the cached KV back to prefill**, AND transform
  decode-layout → prefill-attention-layout. **This reverse path does not exist**:
  the only KV bridge (pdSeparate egress/ingress, e2e relay) is **prefill→decode,
  one-way**, prefill has no "attend over injected prior KV" input, and the layout
  transform is the inverse of the one that exists.

So "transfer-free reuse" holds only for mode (a). Parallel reuse needs a
decode→prefill reverse bridge that neither model has (more natural in pdSeparate,
since the KV is already host-resident).

## Where reuse is computed — prefill vs decode kernel (WSE-specific)

An axis ORTHOGONAL to the storage tier: for a cache-hit, *which kernel* does the
work? On GPU this is a non-question — prefill throughput is 10–100× decode and KV is
cheaply referenced in shared HBM, so you always prefill. **On WSE it must be decided
explicitly, and the GPU default often inverts.**

**The enabling fact (measured, same e2e device run — apples-to-apples):**
- decode = **2240 tok/s** (446 µs/tok, serial autoregressive)
- prefill = **5880 tok/s** (256 tok in 43.5 ms → 170 µs/tok amortized)
- **ratio ≈ 2.6×**, NOT the 10–100× of GPU.
- *Why:* WSE keeps all weights resident in on-chip SRAM, so decode is not
  HBM-bandwidth-starved the way a GPU's tiny-batch decode is → decode throughput sits
  much closer to prefill. This small ratio is what makes "reuse in decode" viable.

**Scenario (multi-turn chat).** A new request shares a prefix (cache hit up to some
seq_len) with an earlier one, and the warm KV is mostly *just-decoded* tokens → it is
**already resident in the DECODE kernel**. Two ways to serve the uncached new turn
(`L_new` tokens) on top of the warm history (`L_warm` tokens):

- **Option A — ship warm KV to prefill + partial-prefill the new turn.** Cost ≈
  `move(L_warm)` + `prefill(L_new)` (+ send the new KV back to decode). Needs the
  decode→prefill reverse bridge + layout transform (does not exist). Move is on-fabric
  for same-chip (e2e) or a host round-trip for cross-chip (pdSeparate).
- **Option B — keep KV in decode, force-decode the new turn in place.** Feed the new
  prompt tokens as forced (teacher-forced) decode steps that append KV without
  sampling. **No move.** Cost ≈ `L_new × 446 µs`. Smaller build than A (decode already
  appends KV per step; just needs a forced-token input).

**Fact-check of Le's claim ("keeping KV in decode + force-decoding may win when KV
transfer is slow") — CONFIRMED.** Breakeven (Option B wins when
`L_warm × move_per_tok > L_new × 276 µs`, where 276 µs = the force-decode compute
penalty per new token = 446 − 170):

| KV-move regime (eff. BW) | move µs / warm-tok | Option B (force-decode) wins when |
|---|---|---|
| current single-stream (~29.4 MB in ~2 s ≈ 15 MB/s) | ~7800 | `L_warm/L_new > 0.035` → **essentially always** |
| optimized multi-stream (~1 GB/s) | ~115 | `L_warm/L_new > 2.4` → **typical chat** |
| ideal 4-ch RoCE (~4 GB/s) | ~29 | `L_warm/L_new > 9.6` → long conversations |

So for multi-turn chat — **large resident history, small new turn** — Option B
(force-decode in place) wins across every transfer regime. It is most decisive for
**pdSeparate** (cross-chip move = seconds, single-stream-bottlenecked at ~15 MB/s by
the serial colmux, not wire BW). The GPU instinct (always ship to prefill) is wrong
here precisely because (1) prefill is only ~2.6× decode, and (2) the move scales with
the *large* history `L_warm` while the compute penalty scales with the *small* new
turn `L_new`.

### Method — how the penalty and breakeven are derived (reusable when numbers change)

**Inputs** (measure/estimate; current values shown — re-measure per config/weights):

| symbol | meaning | current value | source |
|---|---|---|---|
| `t_dec` | decode time per token | 446 µs | e2e device run (2240 tok/s = 1e6/446) |
| `t_pf` | prefill time per token, amortized | 170 µs | e2e device run (43534 µs ÷ 256 tok) |
| `B_tok` | KV bytes per token | 112 KB | `2·n_layers·n_kv·head_dim·bytes = 28·8·128·2·2` |
| `BW` | effective KV-move bandwidth (path-dependent) | host ~15 MB/s→4 GB/s · on-chip fabric ~4.4 GB/s/link | see "Bandwidth regimes" below |

**Derived quantities:**
- **Force-decode penalty per new token** `Δ = t_dec − t_pf` (= 446 − 170 = **276 µs**).
  Rationale: force-decoding one new prompt token runs a full forward + KV append ≈ one
  decode step (`t_dec`), minus sampling (small, ignored); prefilling the same token
  costs `t_pf`. So `Δ` is the *extra* time to ingest a token via serial decode instead
  of parallel prefill.
- **Move time per warm token** `m = B_tok / BW`.

**Cost model** (serve `L_new` new tokens on top of `L_warm` resident warm history):
- Option A (ship-to-prefill): `C_A = L_warm·m + L_new·t_pf`
- Option B (force-decode):    `C_B = L_new·t_dec`

**Breakeven** — Option B beats A when `C_B < C_A`:
```
L_new·t_dec < L_warm·m + L_new·t_pf
L_new·(t_dec − t_pf) < L_warm·m
⇒  Option B wins when   L_warm / L_new  >  Δ / m  =  Δ·BW / B_tok  ≡  R*
```
Recompute `R*` whenever any input changes:
```python
t_dec, t_pf = 446, 170            # µs/token — MEASURE from a run
B_tok = 28*8*128*2*2              # KV bytes/token = 2·n_layers·n_kv·head_dim·2B(fp16)
for BW in (15e6, 1e9, 4e9):       # effective KV-move bytes/s
    d = t_dec - t_pf              # = Δ
    m = B_tok / BW * 1e6          # µs per warm token
    print(BW, "-> R* =", d/m)     # Option B wins when L_warm/L_new > R*
# 15e6 -> 0.035 ; 1e9 -> 2.41 ; 4e9 -> 9.62
```

**Terms (full glossary).**
- `L_warm` (= `L_history`) — tokens of the reused/cache-hit prefix already resident in
  DECODE (e.g. the conversation so far).
- `L_new` — tokens of the uncached new segment to ingest (the new user turn).
- `t_dec` — wall-clock for one DECODE step (one token): forward + KV append (+ sampling).
- `t_pf` — wall-clock to ingest one token via PREFILL, *amortized* over the batched prompt
  pass (total prefill time ÷ prompt length).
- `Δ = t_dec − t_pf` — force-decode penalty: extra time to ingest one new token by serial
  decode instead of parallel prefill.
- `B` (`B_tok`) — KV bytes produced per token = `2·n_layers·n_kv_heads·head_dim·bytes`
  (the leading 2 = K and V).
- `BW` — effective bandwidth of the KV *move* from where it sits (DECODE) to where it's
  reused (PREFILL); path-dependent (on-chip fabric vs cross-chip host bridge).
- `m = B / BW` — time to move one warm token's KV.
- `R* = Δ·BW/B` — break-even ratio `L_warm / L_new` above which force-decode-in-place (B)
  is cheaper than ship-to-prefill (A). Dimensionless (a token-count ratio).

**Worked example (the 0.035 in the fact-check table)** — current single-stream regime:
```
Δ  = t_dec − t_pf = 446 − 170        = 276 µs
B  = 112 KB                          = 114,688 bytes
BW = 29.4 MB ÷ ~2 s ≈ 15 MB/s       = 14.7e6 B/s
m  = B / BW = 114,688 / 14.7e6       = 7.80e-3 s = 7,800 µs   (the "~7800 µs/warm-tok" column)
R* = Δ / m  = 276 / 7,800            = 0.0354 ≈ 0.035
       (identically  R* = Δ·BW/B = 276e-6 · 14.7e6 / 114,688 = 0.035)
```
Reading: B wins once the warm history exceeds `R*·L_new` = **3.5 % of the new turn** → in
chat essentially always ("→ almost always"). At 1 GB/s `R* = 276/115 ≈ 2.4`; at 4 GB/s
`276/29 ≈ 9.6`.

**What R\* means / direction of effect.** R* is the history-to-new-turn length ratio at the
tipping point; **larger R\* ⇒ B (force-decode) wins *less* often** (more history needed to
justify not moving). Because `R* = Δ·BW/B`:
- faster move (`BW↑`) → `R*↑` → B wins less (moving is cheap → ship-to-prefill attractive);
- bigger KV/token (`B↑`) → `R*↓` → B wins more (moving is expensive);
- bigger penalty (`Δ↑`) → `R*↑` → B wins less.

**Bandwidth regimes — where the `BW` numbers come from** (only the first is measured):
- **~15 MB/s — cross-chip host bridge, as-built (measured-ish).** pdSeparate's device KV
  transfer moved the full 29.4 MB in "a few seconds" (STATUS.md); ~2 s → 14.7 MB/s. This is
  the *single on-chip stream* rate, bottlenecked by the serial colmux/adaptor PE, NOT the
  wire — hence far below RoCE.
- **~1 GB/s — cross-chip host bridge, optimized (estimate).** Target if S4 multi-stream
  removes the single-PE serialization. Not measured.
- **~4 GB/s — host RoCE ceiling (nameplate).** 4-channel RoCE (~1 GB/s/ch × 4). Idealized.
- **On-CHIP fabric (same-wafer move — e2e, or the T1 idle-PE tier) — much faster.** Cerebras
  WSE-3 advertises **214 Pb/s ≈ 27 PB/s** aggregate on-wafer fabric over 900,000 cores at
  **1.1 GHz**, single-cycle nearest-neighbor latency. Derived (per-link not officially
  published): **~30 GB/s per PE** (214 Pb/s ÷ 900k) and **~4.4 GB/s per link per direction**
  (one 32-bit wavelet/cycle × 1.1 GHz); a bulk move parallelizes over many PEs/links → tens
  of GB/s to ~PB/s aggregate. Sources: Cerebras HotChips 2024 deck; product page
  (`cerebras.ai/chip`); Introl CS-3 guide.

**Same-chip vs cross-chip — the real fork.** Plugging an on-chip fabric `BW` (≥ ~4.4 GB/s,
far higher in parallel) into `R* = Δ·BW/B` gives `R* ≥ ~10` (up to hundreds): on-wafer,
moving KV is so cheap that **ship-to-prefill (A) wins for all but extreme histories**. So the
force-decode-in-place (B) advantage is really a **cross-chip (pdSeparate, host-path
~15 MB/s) phenomenon**, driven by the slow host bridge — not fabric cost. On one chip (e2e)
the fabric move is fast and A would usually win *if the decode→prefill reverse bridge
existed* (it does not; see [[standalone-vs-integrated-kernel-parity]]). Caveat: the
per-link/per-PE fabric figures are derived from the advertised aggregate + clock, not an
officially advertised per-link number.

**Model assumptions** — each makes Option A look *better* than reality, so B's win is
conservative: (i) ignores sending `L_new`'s KV back prefill→decode (extra A cost);
(ii) `t_pf` is amortized at 256 tokens — for small `L_new` prefill is less parallel so
`t_pf → t_dec`, shrinking `Δ` and `R*`, favoring B more; (iii) force-decode ≈ a decode
step (skips sampling). To re-anchor: pull `t_dec`/`t_pf` from a run's per-token +
prefill TSC lines, `B_tok` from the config dims, and `BW` from the measured KV egress/
ingress time (`bytes ÷ seconds`).

**Caveats / crossover.** (a) Force-decode is SERIAL (latency-bound): a *large* `L_new`
(e.g. a pasted document) costs `L_new × 446 µs` and prefill's parallelism can win —
crossover when `L_new` is large relative to `L_warn`. (b) Numbers are mock-weight,
bsz=1, e2e 512/256; the ~2.6× ratio is architectural but batch/config can shift it
(larger batch amortizes prefill's fixed cost → ratio widens → Option A relatively
better). (c) Neither path is built: Option B needs a forced-token decode input;
Option A needs the reverse bridge. (d) The "~2 s" transfer is a current single-stream
artifact (S4 multi-stream would cut it ~N×) — but even at wire speed Option B still
wins for typical chat ratios.

## Cost anchors (device, test_device_2x2blk_kv, Pw=512)

- On-chip resident KV: **112–448 B/PE** (tiny vs decode region 34,320 B/PE; weights
  dominate; ~14.8 KB/PE headroom at these seq lengths).
- Full request KV volume: **7.34M wavelets = 29.4 MB** (K+V, 256-tok prompt).
- Recompute (evict path): prefill run **~5.7 s** — but see the **≤~512-token prompt
  cap** ([[e2e-pdSeparate-device-validation]]): the current prefill kernel's
  `~200·s²` score/mask buffer means a long prompt can't even be prefilled in one
  pass, which undercuts the long-context PD-disaggregation use case.
- Reload (preserve+reuse, T2): one ingress stream ~29 MB, "few s", no prefill
  compute. Host I/O already 4-channel RoCE.
- General rule: recompute cost ∝ prefill FLOPs, reload cost ∝ KV bytes → **preserve
  wins increasingly as prompt length and model size grow.**

## Related work

- **InferCept** (Abhyankar, He, Srivatsa, Y. Zhang, H. Zhang, 2024),
  <https://arxiv.org/abs/2402.01869> (`arxiv 2402.01869`). GPU-serving analog of
  this exact tradeoff for *augmented* LLMs: when generation pauses for a tool call,
  current systems discard + recompute (wastes 37–40% of forward time). InferCept
  picks, per interception, the **min-waste** action among **preserve (keep in GPU
  mem) / swap (offload to host) / discard (recompute)** → 1.6–2× throughput. Maps
  directly onto the T0/T2/T3 tiers above. The **WSE-3 twist**: an extra **T1
  idle-PE tier**, and the PD-disaggregation **one-way-bridge** constraint that
  makes decode-generated KV hard to reuse via prefill.

## Open questions

- Quantify **T1 (idle-PE offload)** cost: fabric BW for the KV move, addressing a
  parked KV band, how many PEs are free per config — vs T2 host round-trip.
- **Prefer force-decode-in-place (Option B) for multi-turn reuse** (fact-checked win
  for large-history/small-new-turn); build the **forced-token decode input** — the
  smaller change vs the decode→prefill reverse bridge (+ layout transform) that
  Option A needs. Reverse bridge only pays off for large new-input segments.
- Prototype **T0.5 in-bank multi-request reuse**: partition/key the decode KV bank for
  >1 request + `round_reset` retain+extend; quantify how many requests fit the bank
  (SRAM) and the addressing cost. Decide prefill-vs-decode home.
- Attack the **quadratic prefill score/mask buffer** so long prompts (the PD
  long-context use case) can be prefilled at all.
- Add a keyed KV store + skip-prefill-on-hit; port an InferCept-style cost model
  with WSE-3 tier costs. Concrete standalone hook: retain `inj_xk/inj_xv` in a keyed
  host store and make `round_reset` (`decode.csl:265-281`) conditionally retain+extend
  a prior KV instead of always rewinding `iter_num` — the per-round KV-ingress reload
  transport is already there.

## Last updated

2026-07-06 — expanded Method with term glossary, worked R*=0.035 example,
R* direction-of-effect, and bandwidth-regimes incl. WSE-3 on-chip fabric
(214 Pb/s / ~4.4 GB/s per link) and the same-chip-vs-cross-chip fork.
2026-07-05 — from device-validation session (see [[e2e-pdSeparate-device-validation]]).
