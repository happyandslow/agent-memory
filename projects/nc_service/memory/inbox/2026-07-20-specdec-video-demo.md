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
