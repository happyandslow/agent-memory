---
summary: How to choose the on-wafer movement algorithm for a WSE-3 CSL kernel — the decision runs on whether the CE is in the data path (it costs 19-62x the wire) and whether the role being handed between PEs is exclusive. Covers the three role-handoff mechanisms (local filter / K=1 sweep / K=2 baton), the measured cost constants, and a worked example.
tags: [waferengine-staging, csl, wse-3, fabric, routing, switch, control-wavelet, filter, comm-pattern, performance-model, algorithm-selection]
---

# On-wafer communication algorithms — choosing the movement, not just the channel

## The situation this applies to

You have to move data between PEs inside a block and you are about to ask "how
many colours can we afford?" — or you have priced a transfer by counting hops and
colours and the number looks either suspiciously good or suspiciously bad.

Symptoms that put you here:

- a transfer where **many PEs each send their own distinct payload** and the
  senders sit on each other's paths, so no single static route works;
- a design note concluding "this needs N colour pairs and the budget does not
  exist";
- a cost estimate built from **hop counts** with no per-hop cost behind it;
- a relay chain that is "obviously" fine because the wire is fast.

**The usual first framing — colours — is usually the wrong axis.** Get the two
questions below right and the colour count typically falls out as small.

## The two questions that decide it

### 1. Is the CE in the data path?

This dominates everything else. Measured on real CS-3 (M3 Exp-A/B/C, 51 appliance
jobs, max spread 1 cycle; see `inbox/2026-08-23-m3-perf-model-coefficients.md`).
Units are u32 words:

| path | cost |
|---|--:|
| wire, router → router | **0.7 cyc/word** |
| router hop latency, **no CE** | **2.0 cyc/hop** |
| CE receive, bulk fabin-DSD | **13.0 cyc/word** |
| CE receive, per-wavelet data task | **43.6 cyc/word** |
| one clean link, device | 3.91 GB/s = 0.89 wavelet/cyc |

> **A CE-mediated relay runs at 1/19 to 1/62 of wire rate.** That note's own
> summary: *"the wire is ~39x under-used; coefficients price per-wavelet CE
> involvement, which the DSD variants remove."*

So: a store-and-forward chain (`rx=NORTH, tx=RAMP` then re-emit on another
colour) puts the CE in every hop and is one to two orders of magnitude off the
wire. A router-only path (`rx=NORTH, tx=SOUTH`, or `tx={RAMP, SOUTH}` with a
filter) does not. **Count CE-touching hops, not colours.**

### 2. Is the role being handed between PEs exclusive?

A PE changes behaviour partway through a transfer (transit → inject, transit →
take). How it learns to change is forced by two properties, not by taste:

| role exclusive? | must the handoff cross the PE that just stood down? | mechanism | traffic |
|---|---|---|---|
| **no** | — | **local counter (filter)** | **zero** |
| yes | no — successor's token is born locally | **`K=1` sweep** | 1 wavelet, 1 hop |
| yes | yes | **`K=2` baton** | 1 wavelet, 2 commands |

- **Injection is inherently exclusive** — only one PE may drive a line at a time.
  **Reception is inherently not** — each PE takes its own window and they do not
  conflict. That asymmetry is why a send side needs a token and a receive side
  needs none.
- **The baton test.** A role whose `rx` is `RAMP` is **opaque to everything
  upstream on that colour — data and control alike**. That is a sufficient
  condition for "the handoff must cross it", hence for `K=2`. The KV-egress
  gather needs `K=2` for exactly this reason (`pos_emit = RAMP→EAST` would
  otherwise block every later baton). A sweep whose token is born *downstream* of
  every already-fired PE needs only `K=1`. **Measured (demo 03): under
  `POP_ON_ADVANCE` a payload of K commands advances exactly the next K
  advance-capable PEs in path order** — so the extra cost of "the outgoing PE
  must revert too" is one extra command, not an extra wavelet.
- **A fourth constraint, independent of K:** a token needs a **clear channel from
  origin to target**. Any advance-capable PE in between consumes it under
  `POP_ON_ADVANCE`; under `NO_POP` every one of them advances. This is a property
  of the whole line's schedule, and it is what usually kills a token-based
  receive side.

## Mechanism facts these rest on

- **`SWITCH_ADV` changes `rx`, not just `tx`, and does it at the router.** WSE-3
  has an input switch *and* an output switch (`target/wse3.csl:282-284`), each
  position carries its own input select (`:273`), and one control wavelet advances
  both on the same cycle (official router trace,
  `Cerebras_Docs/debug/debugging.md:500-509`). **They advance together** — you
  cannot step `rx` without stepping `tx`.
- **A route change needs no CE.** It happens at the router as the wavelet passes;
  even a pure-transit PE re-routes for subsequent wavelets. And an input queue
  claimed by a pending fabin microthread still executes a router-level
  `SWITCH_ADV` — only the CE tap vanishes `[sim-observed]`. **So a route can be
  flipped while the PE is mid-receive.**
- **A filter is a FABRIC behaviour.** SDK Topic 8: *"Fabric filters … specify the
  wavelets to allow to be forwarded to the CE"*, configured beside `.routes` in
  `@set_color_config`. **Rejected wavelets never reach the CE**, so a 2-tx
  `tx={RAMP,SOUTH}` receiver costs its CE nothing for traffic that is not its own.
- **Two filter kinds, and the choice is usually forced.** `range` selects on the
  data wavelet's **upper 16 bits** (`builtins.md:2041-2044`) — unusable when those
  bits are payload (e.g. 2×f16 packed). `counter` selects on arrival count with a
  periodic pass/drop and a per-PE initial phase — the one to reach for.
- **Only 16 of 24 colours can carry a switch:** `{0-9, 12, 13, 16, 17, 20, 21}`
  (`memcpy/sys_params.csl:42-43`). Check this *before* picking an id — it is a
  tighter constraint than the free-colour count.

## Worked example — a multi-sender equidistant shift

![worked example](figures/2026-09-09-comm-algorithm-worked-example.png)

**Setting.** One column of 256 PEs. Rows 0-127 each hold their **own distinct**
p = 5 words and must deliver to row k+128. Every source therefore sits on every
upstream source's path. 128 such columns run independently.

**The floor.** Every transfer crosses the single link between row 127 and row 128,
so `128 × 5 words × 0.7 cyc/word ≥ 448 cyc` bounds *any* algorithm. **Only
shrinking the payload beats a min cut** — which in this instance it did: 71 % of
the original payload turned out to be a Y-replicated quantity that every
destination wanted identically, i.e. a router multicast rather than 128 transfers.
**Always ask whether the payload is really distinct per destination before
designing the movement.**

**Sender side — exclusive role, `K=1` sweep.** Two switch positions
(`rx=NORTH,tx=SOUTH` transit / `rx=RAMP,tx=SOUTH` inject), `ring_mode=false` so a
fired sender sits at its last position and becomes immune, `POP_ON_ADVANCE`, one
1-hop `SWITCH_ADV` per handoff ≈ 2 cyc with no CE round-trip. All 128 inject DSDs
are **armed at layer start**, so CE work is 128-way parallel and only the drain
serialises `[the pre-arm/backpressure behaviour is inferred, not verified]`.

**Receiver side — non-exclusive role, filter, zero coordination.** Static
`rx=NORTH, tx={RAMP,SOUTH}` (1-tx sink at the last row, or the stream leaks past
the region), plus a counter filter whose period is the whole stream and whose
per-PE phase is `j·p`. No switch, no tokens. Each CE sees only its own 5 words.

**Why the receiver *cannot* use a switch — the general lesson.** Receiver *j*
would need its advance while senders *j*+1…127 are still unfired and therefore
advance-capable; any token aimed at the receive band is eaten by the first of
them, and `NO_POP` would advance all of them at once. A different colour cannot
help: a `SWITCH_ADV` advances the switch of **the colour it travels on**, and the
data must be on that colour. So **while any sender is unfired, no token can reach
the receive band** — which forces the receive side to be coordination-free.

**Outcome.** Store-and-forward fold at its affordable colour budget: 4,160-13,952
cyc/column/layer. Switch+filter: ~704. A 6x-20x gap that a hop-and-colour cost
model had scored as 25 %.

## The five scenarios, in full

Each is a runnable mini-geometry (4–5 PEs, `./commands_wse3.sh`, asserts against
an oracle). All five compile and pass **in the simulator**; none has been run on
device. Code lives in
`/home/lexu/wse3-performance-model/demo/communication-algorithm/`, one directory
per demo, and each directory's `README.md` carries the operational detail —
register values, run instructions, per-demo gotchas — that is deliberately kept
out of this file.

**How to read the figures.** An arrow drawn over a PE **is** that PE's routing
entry for that colour. Arrow colour == fabric colour, so an algorithm's colour
count is readable straight off the picture. `ramp` in a route means the arrow
connects to the box — rising **out** of it (the PE is feeding the wire) or diving
**into** it (the wavelet is delivered here); as an *output* alongside another it
is 2-tx, drawn as a line passing over **and** teeing in. A control wavelet rides a
fabric colour like any other, so it is drawn on that colour's line with only its
**head in red** — red marks "carries a command", it is never a colour and never
counts. Where a routing table is repainted mid-run, both time slices are drawn.
Sources: `docs/diagrams/commlib.py` and `gen_2026-09-09-demo0*.py`.

---

### 1 · Many receivers, each needing a different slice of one stream

*Non-exclusive role → local counter → **zero** coordinating traffic.*

![demo 01](figures/2026-09-09-demo01-filter.png)

Every wavelet is offered to every receiver (`west - ramp+east` is 2-tx: the router
hands it onward *and* offers a copy to the PE). What makes that free is that the
**filter sits in the fabric, not in the PE** — a wavelet outside this receiver's
window is dropped before the compute engine sees it, so each CE runs for 3 words
and not 12.

Taking is not exclusive: two receivers wanting different words do not conflict, so
nobody has to be *told* when their turn is — a counter already knows.

**What it pinned down: `max_counter` is INCLUSIVE**, while `builtins.md` words it
"(exclusive)". Built to the doc, every receiver took **four** words and the fourth
ran off the end of the buffer — which reads as a bug in whatever consumes the
data, not as a filter bug. See `01-filter-window/` for the phase arithmetic.

---

### 2 · Many senders, one wire, only one may drive it

*Exclusive role, successor's token born locally → **K = 1** sweep.*

![demo 02](figures/2026-09-09-demo02-sweep.png)

Two switch positions per sender; one `SWITCH_ADV` per handoff, travelling exactly
one hop. All senders arm their inject DSD at the start — three of them are at
`west - east`, so the router refuses their RAMP input and the microthread parks on
backpressure until its switch opens. CE work is therefore N-way parallel and only
the drain serialises.

`K = 1` suffices because sender *j*'s successor's data **and** token are both born
east of it: nothing ever has to cross a PE sitting at `ramp - east`.

**What it pinned down: the pre-arm claim holds.** An armed microthread parks on a
closed route and drains the instant a `SWITCH_ADV` opens it. That had been the
single largest unverified assumption in the design it came from.

---

### 3 · A handoff where the outgoing PE must also stand down

*Exclusive role, handoff must cross the PE that stood down → **K = 2** baton.*

![demo 03](figures/2026-09-09-demo03-baton.png)

A probe, not a design. Three PEs all start able to take a copy; the head sends one
payload of K commands, then one data word; whoever is still in the take state
records it, so the recorder count reports how many advanced.

**What it pinned down:** under `POP_ON_ADVANCE`, **K commands advance exactly the
next K advance-capable PEs, in path order** (K=1 → 1, K=2 → 2). So the extra cost
of "the outgoing PE must revert too" is one extra *command*, not an extra wavelet.

Note the shape it is built around: pos0 is take **and** forward. It has to be — a
PE whose only output is `ramp` is opaque to everything behind it. The same trap in
its `rx` form is why a receive side cannot use a token at all.

---

### 4 · The same job as 2, built the way the shipped K-pipe builds it

*The fold on a pure move — where it only ever costs.*

![demo 04](figures/2026-09-09-demo04-fold.png)

Count the arrows touching each box: on every hop the words leave the wire, enter
the PE, and are pushed back out. Two colours, because a relay must **receive and
send at the same instant** — and note what that is *not*: not the
one-rx-per-colour rule. A switch gives one colour both routes over *time*; a
streaming relay needs them *concurrently*.

The tags read 3, 6, 9, 12 — the stream **grows**, so the cut carries `N·p` exactly
as it would with pure routing. Nothing is bought for the 19–62× CE bill.

---

### 5 · The collector needs a SUM, not the words

*The fold where it is the mechanism, not the cost.*

![demo 05](figures/2026-09-09-demo05-reduce.png)

Identical wiring to demo 4. What changed is what the PE does between the two
arrows: `@fadds(send, recv, local)` — receive, add your own, emit one partial.

Two things follow, and both favour the fold. A switch-routed path **cannot do this
at all** (the router moves wavelets; it cannot add them). And the tags now read
3, 3, 3, 3 — the stream **never grows**, because each hop turns two inputs into
one output, so the cut carries `p` and not `N·p`. At N = 128 that is a 128×
saving on the wire, the opposite direction from demo 4.

Demos 4 and 5 are the same picture with different tags, and that is the whole
fold-vs-switch test in one image pair.

## Checklist

1. Is the payload actually distinct per destination, or is it replicated? A
   replicated quantity is a router multicast, not this problem.
2. Draw the min cut. It bounds every algorithm and it is cheap to compute.
3. Count **CE-touching hops**, not colours. If the CE is in every hop, that is
   the number, and colours are a second-order lever.
4. For each role change: exclusive? does the handoff cross the stood-down PE?
   → filter / `K=1` sweep / `K=2` baton.
5. Check the token has a clear channel to its target.
6. Only now pick colour ids — and if a switch is needed, from the 16 capable ones.

## Pointers

- Full derivation, with the corrections it went through:
  `/home/lexu/wse3-performance-model/analyses/2026-09-08-equidistant-shift-colour-vs-performance.md`
  (§3 min cut, §13 the CE/wire asymmetry, §14 the algorithm by role)
- Session record: `/home/lexu/wse3-performance-model/docs/reports/2026-09-08-4b-comm-pattern-session-report.md`
- Figure source: `/home/lexu/wse3-performance-model/docs/diagrams/gen_2026-09-09-comm-algorithm-worked-example.py`
- Related: [[csl-control-payload-mechanisms]] (the control-wavelet/switch/filter API
  surface), [[switch-scatter-vs-parity-shift]], [[m3-idle-pe-tier]] (where the cost
  coefficients were drained)
- Skill: `cerebras-kernel-comm-patterns` is the pattern taxonomy; **this topic is
  the cost-and-mechanism layer under it, and is a promotion candidate into it.**

## Not established

- **[RESOLVED in sim 2026-09-09, demo 02]** the pre-arm + backpressure behaviour:
  armed microthreads do park on a closed route and drain the instant a
  `SWITCH_ADV` opens it. Not yet confirmed on device.
- Whether a fabric-dropped wavelet costs the router any cycles.
- The filter's register encoding counts **half-wavelets** at the `tile_config`
  level; demo 01 configures it from the layout instead and did not have to face
  that. An odd wavelet count per window on the runtime path is unexplored — same
  risk class as the odd-extent silent hang.
- Whether any of the four demos behaves the same on device as in the simulator.

## Last updated

2026-09-09 — created from the `4b-comm-pattern` session (wse3-performance-model);
same day, added the five runnable demos, the three facts they measured, and the
fold-vs-switch test with its application to the shipped K-pipe.
