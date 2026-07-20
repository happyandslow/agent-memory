# Spec-dec video demo (GPU + CS-3) — built, and an acceptance-rate modelling trap

Date: 2026-07-20
Artifact: `nc_service/demo/specdec_race/index.html` (self-contained, no deps)
Spec: `nc_service/docs/superpowers/specs/2026-07-20-specdec-demo-design.md`

## What it is

Single-file browser demo for screen-recording during talks. Two panes race to the
same token budget: GPU alone (metronome, 9.2 ms/tok) vs GPU + Cerebras (bursty,
one block per round). Spec pane crosses the line first; both freeze on a final
frame showing finish times and the speedup.

All timing constants are live-tunable, each tagged `measured` / `derived` /
`estimated` in the UI. The renderer computes no timings: it consumes RoundEvents
from an `Engine` interface (`setParams`, `async nextRound(i, startMs)`,
`dispose`), so a `LiveEngine` backed by the real verify service drops in without
touching rendering. `SimulatedEngine` runs in a background producer loop feeding
a bounded queue ahead of the virtual clock — the same async shape a network
engine needs.

## THE TRAP: "acceptance rate 0.62" is ambiguous and it matters ~3x

At K=16 the two readings disagree violently:

| model | meaning | tokens/round | speedup |
|---|---|---|---|
| `blockFraction` | 62% of the block lands | 9.92 + 1 = 10.9 | **3.16x** |
| `geometric` | per-token p, stop at first reject, `(1-p^(K+1))/(1-p)` | 1.63 + 1 = 2.63 | **0.76x — SLOWER than the GPU alone** |

`geometric` is what standard speculative decoding actually does, and it is what
GLM's measured `accept_rate 0.80` / `accept_len 1.80` at K=1 means (1 + 0.8 = 1.8
confirms it is per-token). Under it:

- **break-even p = 71.1%** at our stage timings
- **p ~= 0.93** is what our claimed "~10 accepted per round" implies

So the repo's "~10 accept/round at K=16" is only consistent with a per-token
acceptance around 0.93, which is a strong claim. If the real CS-3 draft lands
nearer 0.62 per-token, **the system is a net loss** at these stage costs. Both
models ship in the demo, selectable, always labelled. Still no measured CS-3
acceptance rate — this remains the single biggest unvalidated number.

## Round composition used (and its caveat)

draft 14.0 (3.5 + 15x0.70) + gateway 3.2 + GPU leg 1.36 + verify 13.2
(= 9.2 + 16x0.2516) = **31.8 ms** at K=16.

Verify is a two-point linear fit through the only two measured points (1 tok
9.2 ms, 32 tok 17.0 ms); the fit reproduces both exactly. The composition sums
stages from **two different campaigns** — the 18.3 ms driver-side round was
measured without a GPU verifier attached, and the 3.296 ms verify-side figure
was against the *passthrough* kernel, not the real one. Defensible, but it is a
composition and the demo says so.

`pipeline.overlap` (draft block n+1 during verify of block n) is exposed as an
idealised upper bound: period becomes max(draft, net+verify) = 17.8 ms, giving
5.65x. Not implemented anywhere, purely a what-if knob.

## Verification (no browser on this box)

Ran the real script against a stubbed DOM in node. Confirmed: both panes land
exactly on the budget; spec wins 1.18 s vs 3.68 s; simulated 3.13x vs analytic
3.16x (<1% drift); byte-identical across takes with a fixed seed (1175.284 ms
both runs); seed changes outcome; geometric p=0.62 correctly finishes the spec
pane *after* the GPU (0.84x). Two bugs found and fixed this way — an EngineHost
that planned rounds from the wrong origin when parameters changed mid-run, and a
finish condition that fired early because the passage was shorter than the race
distance.

## Next

- Measure real acceptance rate on CS-3 — everything above hinges on it.
- Implement `LiveEngine` against the real verify service when it is wired up.

## Update (same day): two rendering bugs the screenshot caught

Screenshot showed the spec pane **completely empty** at 400/400 tokens. Two
distinct bugs, both invisible to the node/DOM harness until I checked node
retention explicitly:

1. **CSS animation clobber.** `.tok` held itself on screen with
   `animation: pop ... forwards` over a base `opacity: 0`. Promoting an accepted
   token to `.landed` replaced that animation with `flash .6s` (no `forwards`),
   so every committed token reverted to the base `opacity: 0` and vanished ~0.6 s
   after landing. Lesson: never let an animation be the thing that HOLDS an
   element visible — make the base state visible and let animations only handle
   the entrance.

2. **Commit-after-reveal ordering.** `advance()` revealed the in-flight round's
   drafts BEFORE draining completed rounds. On the tick where the clock crosses a
   round boundary, `inFlight()` already returns the NEXT round, so the
   round-change branch called `clearDrafts()` and wiped the completing round's
   draft nodes before they could be promoted to committed. Only the bonus token
   survived per round — 14 disjointed words for 120 tokens. Fix: drain/commit
   first, reveal second, plus `revealDrafts(done, done.draftedCount)` at commit
   so a slow frame straddling the drafting phase still materialises every node.

Also: rejected tokens were being cleared ~16 ms after being struck through
(invisible). Now retired one full round later, so the correction is readable.

**Pacing.** Defaults were unreadable: 400 tokens at 0.25x meant a 31.8 ms round
completed in 127 ms real, i.e. 8 accept/reject cycles per second. New defaults
120 tokens at 0.07x -> round ~454 ms real, race records in ~16 s. Streams now
ease-scroll toward the newest line (lerp per frame) instead of snapping, font
up to 17px.

**Harness lesson:** the stubbed-DOM harness passed all timing/finish/determinism
checks while the pane was visually empty. Only an explicit *node retention +
class census* check caught it. Timing assertions do not test rendering.

## Update 2: the "spec pane frozen at 0 tokens" failure (r5)

Second screenshot: right pane stuck at 0 tokens / 0.00x while the mechanism strip
kept advancing to round #11 and the GPU pane ran normally.

**Root cause class: the round queue drifting AHEAD of the virtual clock.** If
every queued round has `startMs > vnow`, then simultaneously: `drain()` returns
nothing (nothing ever commits, counter stays 0), the draft reveal fraction clamps
to 0 (no dim draft tokens drawn), and `renderMech()` still animates because it
reads `inFlight()` off the queue directly. All four observed symptoms fall out of
that one condition.

Reproduced by injecting a 500 ms queue skew into a live run. Without the fix the
pane froze at 11 tokens and the final speedup degraded 3.04x -> **1.30x** — which
also retro-explains the **1.46x** anomaly in the FIRST screenshot. Same bug, milder
instance.

Fix: `EngineHost.align(nowMs)` called at the top of `advance()` — if the queue head
is in the future, slide the whole queue (and `nextStartMs`) back so the next round
starts now. No-op in the normal case, self-healing otherwise.

Also added, because this class of failure is silent:
- `BUILD` stamp in the footer (`build r5 · 2026-07-20`). The demo is hand-synced to
  a Mac (`/Users/lexu/Projects/nc_service/...`) and browsers cache `file://`
  aggressively, so "is this even the new build" was unanswerable.
- A visible stall banner when the GPU is >30 tokens in and the spec pane has
  produced nothing.

**Caveat: the original trigger in the browser is still unidentified.** The fix makes
the condition self-correcting and detectable rather than proving what caused it.

Test suites now: race/finish, determinism+accept-models, node-retention, skew-recovery.

## Update 3 (r7): continuous mode — the demo is a BACKDROP, not a clip

Corrected requirement from Le: keep the PACE as-is (it is the realistic UX), but
make the OUTPUT long, so the page is still scrolling while the room is talking.
My earlier reading ("too fast") was wrong; the complaint was that the text ran out.

- `sim.endless` (default ON): `maxTok = Infinity`, so neither pane ever crosses a
  finish line and both scroll indefinitely. Turn it off for the fixed-distance
  race with a winner and a frozen final frame.
- Speed restored to 0.07x, landing/entrance animations restored to r5 values.
- Passage expanded to **646 tokens** of on-message prose. It still loops: GPU pane
  every ~85 s, spec pane every ~27 s (it consumes ~3x faster). Acceptable for a
  backdrop, but that is the repeat period if it ever needs to be longer.
- `trimStream` caps each pane at 700 nodes AND compensates `scrollTop` by the
  height removed — without that, pruning yanks the view upward every few seconds.

### Two real bugs surfaced by the 6-minute soak

1. **`LOOKAHEAD` 8 was too shallow.** Under producer starvation the spec pane
   under-produced and the speedup sagged 3.14x -> 2.09x *without any visible
   error*. Raised to 64. A live network-backed engine will starve far more easily
   than the simulated one, so this matters beyond the test.
2. **Negative frame delta.** `dtReal = Math.min(now - last, 100)` had no lower
   bound. A backwards clock drives `vnow` negative, which puts the entire round
   queue in the future — **exactly the r5 "spec pane frozen at 0 tokens" symptom**.
   Now clamped to `Math.max(0, ...)`, and `reset()` re-seeds `lastFrameMs`. This is
   a plausible root cause for that browser freeze, though still not proven to be
   the one that fired.

Suites 2-5 had to be told `sim.endless=false` — they assert a race that finishes.
Failing suites after a default change are not automatically regressions; check the
assumption before "fixing" the code.

## Update 4 (r8): every number is an editable, persistable, shareable interface

Le's point: the architecture is still changing, so all these constants WILL change —
don't bury them in sliders. Added:

- **Exact numeric entry** next to every slider. A slider cannot express 14.03, and
  measured values arrive as exact numbers. Typing a value outside a slider's design
  range widens the track instead of silently clamping the entry.
- **Editable provenance.** Click the measured/derived/estimated badge to cycle it.
  The footer honesty note reads the acceptance rate's *current* label, so once that
  number is genuinely measured on CS-3 the warning stops shouting by itself.
- **localStorage persistence** (guarded — some browsers block it on `file://`; the
  panel says so and falls back to copy/apply).
- **Config JSON round-trip.** Export/import the whole config. Accepts a full export,
  a bare `{"key": value}` map (send only what changed), or a provenance-only update.
- **Named presets** — bank one per architecture revision, switch live on stage.

Two design bugs the tests caught, both the same shape: `applyConfigJson` rejected
legitimate inputs because it counted only changed *params*. A provenance-only update
("we measured it, relabel it") and an explicit empty `provenance: {}` ("clear the
labels") both threw. Fix: key on the *presence* of the field, not its size.

Also refactored the panel row from `innerHTML` string building to DOM calls — it was
untestable under the stub, and the code is cleaner for it.

### Parameter-tuning guidance worked out for Le (sweeps in scratchpad/sweep.js)

- **The two acceptance models disagree about K in OPPOSITE DIRECTIONS.** Block
  fraction rewards larger K without bound (4.83x at K=64) because it assumes accepted
  scales linearly with K — a modelling artifact. Geometric has a real optimum at
  **K≈8-12** and DEGRADES past it (0.79x at K=64), because everything after the first
  rejection is discarded. Any "what K should we pick" discussion must use geometric.
- **Stage ablation at K=16 (blockFraction 0.62), zeroing each stage:** GPU<->gw leg
  3.16 -> 3.30x, gateway 3.16 -> 3.51x, verify base 3.16 -> 4.45x, overlap ON
  3.16 -> 5.65x.
- **NARRATIVE CORRECTION:** "network is 41%, wafer is 5%" was the PASSTHROUGH-kernel
  result. With the real 28-layer kernel, draft 14.0 + verify 13.2 = **85%** of the
  round and gateway+leg is only ~14%. Stop using the old framing in talks.

## Update 5 (r9): TTFT/TPOT naming, and the round decomposition audited for double-counting

Le asked whether `draft.firstTokenMs` (3.5) and `draft.perTokenMs` (0.7) are TTFT
and TPOT. Answer: **one is, one is not.**

- 0.7 ms **is** the draft model's TPOT (steady-state per-token).
- 3.5 ms is **NOT** TTFT. TTFT includes prefill; this is the first step of EVERY
  draft round, paid once per round. It is dearer than 0.7 because per-round fixed
  cost (re-arm, seed/band send, pipeline fill) is lumped into it. *Inference, not a
  measured breakdown.*
- Expanding: `draft = 3.5 + (K-1)*0.7 = **2.8 + 0.7K**` — i.e. 2.8 ms fixed per
  round plus 0.7 ms per token. The fixed part does NOT scale with K, which is
  exactly why larger blocks amortise better.
- **The demo models no prefill/TTFT at all** — both panes start mid-generation.

### Double-counting audit (Le's follow-up: how does 3.5 relate to the transfer overhead?)

They are **disjoint**. The measured mode-B round decomposes as fabric 14.0 +
gateway 3.2 + band/seed 0.6 + TSC drain 0.2 + band build 0.1 = 18.1 ms, and those
sum to the observed round. The 3.5 sits **inside** the 14.0 fabric segment, which
was measured *inside the worker*; the 3.2 gateway hop was measured as
round-minus-worker. No overlap. Likewise `net.gpuLegMs` 1.36 was derived as
verify-side minus driver-side, so it is the segment BEYOND the gateway hop.

Caveat kept on the record: 3.5 is a host-observed receive time, so it already
contains the on-pod d2h movement — it is not pure wafer compute.

**Gap found and fixed:** the model was missing the 0.9 ms of measured host-side
per-round work (band/seed 0.6 + TSC drain 0.2 + band build 0.1). Added as
`net.hostOverheadMs`, a fifth timeline stage. Round 31.8 -> 32.7 ms, headline
3.16x -> 3.07x.

Also: block length was already fully adjustable — no hardcoded 16 anywhere except
the default. Verified draft time stays exactly linear (`2.8 + 0.7K`) for K = 1..256,
and that typing a value beyond a slider's range widens the track instead of clamping.

Refactor: introduced `STAGE_KEYS` + `stageTotal()` as the single stage list. Adding
hostMs required touching five separate places and I missed one (the engine's own
`stages` literal), which the suite caught — hence the single list.

## Update 6 (r10): what `net.hostOverheadMs` actually is, and the "overhead" ambiguity

Source of truth: `memory/topics/specdec-modeb-drive-path.md:129` (Timeline 2, rewind
round ~18.1 ms).

**`net.hostOverheadMs` = 0.9 ms is HOST CPU work, not network** — the key name is a
misnomer (kept for config compatibility; label and note corrected in the UI):
- `band_build` 0.1 ms — host numpy building the continuation-pack re-arm band
  (`repack_continuation_band`). **Was 19 ms** before vectorisation; at that point it
  was ~half the entire round, and the three *hypothesised* levers (batch, nonblock,
  kernel-merge) all missed it.
- `band+seed send` 0.6 ms — pushing that band plus the seed token to the wafer.
- `tsc drain` 0.2 ms — **profiling readback, measured at 0.0 in another run.** So
  ~0.2 of the 0.9 is measurement cost that a production path likely does not pay.

**The "overhead" figure was ambiguous and I stated it misleadingly.** Two defensible
definitions at K=16:
- **5.46 ms** = gateway 3.2 + gpuLeg 1.36 + host 0.9 — "cost outside the draft stage".
- **8.26 ms** = the above + 2.8 — the honest "fixed per round" number, because
  `draft.firstTokenMs` (3.5) exceeds `draft.perTokenMs` (0.7) precisely by per-round
  setup. That 2.8 is overhead by any behavioural definition.

`draft.firstTokenMs` does NOT feed the 5.46; it lives inside the draft stage.

**Fix:** `steadyState` now exposes `fixedMs` / `perTokMs` and the panel shows them, so
the linear structure is visible instead of relying on me to explain it:

    round = fixedMs + perTokMs * K = 17.46 + 0.9516 * K

    17.46 = 2.8 (draft per-round setup) + 9.2 (verify base) + 5.46 (three overheads)
    0.9516 = 0.7 (draft/token) + 0.2516 (verify/token)

Verified identical to the five-stage sum for K = 1..128.

## Update 7 (r11): the 3.5 ms step0 is NOT measurable on the production path

Le pushed back: "shouldn't every token be 0.7? our timer measures the end-to-end
batch, it cannot isolate the first token." **He is right, and this is a real
weakness in the model.** Checking the raw log (`specdec-modeb-drive-path.md:98-99`):

```
perstep nb=0: recv16=13.9(step0=3.4 rest=10.5)   <- split EXISTS
batch   nb=1: recv16=14.1                        <- NO split
```

The step0/rest split only ever existed in **per-step receive mode**. Spec-dec
production uses **batch** receive, which reports one number. So the 3.5 comes from a
DIFFERENT receive path than the one that ships, and cannot be confirmed on the
production path with current instrumentation.

**Two readings fit the measurement equally well at K=16:**
- A: `2.8 + 0.7K` (fixed startup + steady per-token) -> 14.0 at K=16
- B: `0.875K` (uniform per-token) -> 14.0 at K=16

They are indistinguishable at K=16 by construction and **diverge up to 11% elsewhere**
(K=4: A is 10% higher; K=64: B is 11% higher). Speedup at K=64: A 4.78x vs B 4.31x.
So the choice matters precisely for the K-sweep question Le is planning.

**Is the 2.8 double-counted with gateway/host?** No — they are separate fields on the
same log line (`band_build=.. band_send=.. | recv16=..(step0=..) | tsc=..`), and
gateway is `driver_rtt - worker`, measured entirely outside the worker. But whether
the 2.8 is real wafer arm/pipeline-fill or a per-step-mode measurement artifact is
**UNRESOLVED**. To settle it: instrument the batch path, or sweep K on device and fit
the slope/intercept.

Parameter note updated to record this; setting firstTokenMs = perTokenMs models B.

### The physical chain (Le asked what each leg spans)

```
GPU host (verifier)
  | 1.36 ms   net.gpuLegMs   = verify-side 3.296 - driver-side 1.932
CS-3 gateway node (driver runs here)
  | 3.2 ms    net.gatewayMs  = driver rtt - worker time; L7 HTTPS ingress on :443
executor pod (worker)
  |- 0.9 ms   net.hostOverheadMs = pod CPU: band build/send + tsc
  | 14.0 ms   draft (fabric, includes on-pod d2h)
WSE-3 wafer
```

**Campaign inconsistency worth remembering:** the SAME gateway<->worker segment
measured **1.77 ms** in the passthrough campaign (ping 0.96 + gw overhead 0.81) but
**3.2 ms** in mode-B. ~1.8x apart for the same physical hop.

## Update 8 (r12): the GPU-anchored bound catches a cross-campaign inflation

Le's challenge: the verify-side RTT is read inside sglang at the verifier, so by
construction it must contain every overhead except on-wafer compute. **Correct, and
it invalidates the overhead figure I had been quoting.**

```
verify-side 3.296  -  appliance ring 0.166  =  3.13 ms
```

That is the total non-wafer overhead of the draft path, measured AT THE CONSUMER,
so it cannot omit a segment. My demo was carrying **5.46 ms** — 1.75x more than the
entire measured end-to-end overhead.

**Localised exactly.** Same segment (gateway <-> worker, incl. gateway overhead and
worker host work):

| campaign | composition | total |
|---|---|---|
| passthrough | ping 0.96 + gw overhead 0.806 | **1.77** |
| mode-B | gateway 3.2 + host 0.9 | **4.10** |

`gpuLeg` 1.364 exists only in the passthrough campaign. So:
- passthrough-consistent: 1.77 + 1.36 = **3.13** — matches the GPU anchor exactly
- what I had: 4.10 + 1.36 = **5.46** — supported by no single measurement

**Root cause: mixing campaigns.** mode-B's (worse, less stable) transport combined
with passthrough's cross-cluster leg. Round 32.69 -> 30.36 ms and 3.07x -> 3.31x if
the passthrough set is used consistently.

**Added to the panel:** a `non-wafer overhead` row plus a warning whenever it exceeds
3.13 ms, explaining that the bound is passthrough-derived.

### The real caveat

**mode-B never had a GPU verifier attached, so the real 28-layer kernel has NO
verify-side measurement and therefore no bound of its own.** 3.13 bounds the
passthrough system only. The real kernel additionally does per-round band build/send
that passthrough never did, so its true overhead is probably *between* 3.13 and 5.46.
Unproven hypothesis for why mode-B transport is worse: the re-arm band payload is far
larger than passthrough's ~75 bytes, possibly past the latency-bound/payload-invariant
regime.

**The one measurement that would settle it: run the real kernel against a GPU verifier
and read the verify-side RTT.** That is TODO 2(c) in specdec-cs3-roadmap.md and it is
now the highest-value missing number after the acceptance rate.

Raw-data status: driver-side per-round samples (`_runs/full_batch_1000.json`) are NOT
on gala2 any more (may survive on CS-3 under ~/rsync/nc_service-rsync/_runs/);
verify-side raw samples never existed — the GPU service prints aggregates only.
Full record lives in ContextBase `GOZQ9I8pOe`, far more detailed than the topic file.

## Update 9 (r13): collapsed to three overheads — and why verification needs TWO numbers

Le: simplify to three overheads (drafting / verification / communication), keep
acceptance rate and block size, "we'll compute GPU and Cerebras performance and fill
them in". Asked whether that invalidates the simulator.

**It does not.** The simulator only consumes (round total, stage breakdown, accepted
count). Three stages animate exactly as well as five. Given the cross-campaign
inflation found in r12, a single communication lump the user owns is *more* honest
than a five-way split implying precision the data cannot support.

**But I first answered wrong**, assuming they would enter flat per-round totals and
warning that K-scaling would break. Le corrected: they will supply **per-token latency
or throughput**, so why can't it scale? The real answer is an asymmetry:

- **Drafting scales linearly.** Sequential generation, so ms/token is meaningful
  (0.70 ms/tok = ~1430 tok/s).
- **Verification does NOT.** K tokens are checked in ONE forward pass. Measured:
  1 tok = 9.2 ms, 32 tok = 17.0 ms => per-token cost is 9.2 vs 0.53 ms, a **17x
  swing**. Extrapolating from a single per-token figure at K=1 predicts 294 ms at
  K=32 versus an actual 17.0 — wrong by 17x.

So verification needs `fixed + perToken` (9.2 + 0.2516K). **fixed/marginal = 37x, and
that ratio IS the mechanism**: speculation wins by amortising one forward pass over K
tokens. A purely per-token verification model makes speculative decoding impossible in
principle — verifying K would cost the same as generating K.

Final shape: `draft.perTokenMs` + `draft.fixedMs`, `verify.fixedMs` +
`verify.perTokenMs`, `comm.roundMs`, `gpu.decodeMsPerToken`, `draft.K`, acceptance.
Round = 15.13 + 0.9516K; at K=16 that is 30.36 ms and 3.31x (comm now the
GPU-anchored 3.13, not the mixed 5.46). Verified K = 1..128 scales correctly.

Suites 7/9/10 failed on stale assertions (old key names, old 32.7 ms / 17.46 ms
constants) — expected after a model change, not regressions. Updated.
