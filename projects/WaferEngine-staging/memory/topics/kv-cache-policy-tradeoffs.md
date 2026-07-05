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
| **T1 idle-PE SRAM offload** | spare/empty PEs on the *same wafer* | on-fabric gather (router hops, ns–µs, no host BW) | (#free PEs × ~48 KB) — wafer-scale spatial abundance | **wafer-unique middle tier** (Le's idea); needs a park-band + addressing |
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
- Build the **decode→prefill reverse KV bridge** (+ layout transform) to enable
  parallel multi-turn reuse; more natural in pdSeparate (KV already host-resident).
- Attack the **quadratic prefill score/mask buffer** so long prompts (the PD
  long-context use case) can be prefilled at all.
- Add a keyed KV store + skip-prefill-on-hit; port an InferCept-style cost model
  with WSE-3 tier costs. Concrete standalone hook: retain `inj_xk/inj_xv` in a keyed
  host store and make `round_reset` (`decode.csl:265-281`) conditionally retain+extend
  a prior KV instead of always rewinding `iter_num` — the per-round KV-ingress reload
  transport is already there.

## Last updated

2026-07-05 — from device-validation session (see
[[e2e-pdSeparate-device-validation]]).
