# Fabric has no keyed routing — everything is static "orchestration primitives" — 2026-07-16

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured   <!-- captured | drained; Le wants a NEW SESSION to discuss this -->

## What happened / finding

Working through `qwen3_1p7b-prefill/src/prefill.csl`'s KV-egress control wavelet
(`kv_egress_turn2`, `prefill.csl:833`) crystallized a framing worth its own discussion:
**on the WSE fabric there is no keyed/content routing at all; every "many→one" or "route-by-x"
ML operation is instead expressed as a compile-time-fixed topology stepped by deterministic
orchestration.** The control wavelet is one such stepper.

- **Why keyed routing is structurally impossible** (skill `cerebras-kernel-comm-patterns` Gate 1):
  a wavelet carries **no destination field**; routing is a property of a **color's painted route**
  (comptime `fabout_dsd` → queue → color), not of the wavelet. No crossbar that selects an output
  port by content.
- **The router switch is a ≤4-position sequential stepper, not a keyed crossbar.** Per color, a
  switch has ≤4 positions (each = a fixed input→output route) + a current-position pointer. The only
  runtime ops are **advance** (SWITCH_ADV control wavelet; `ring_mode` wraps) and **reset**
  (`clear_current_position`). There is **no "jump to position K by key."**
- **Worked example — KV egress switch-gather (PATTERN B / skill P-4).** A row of PEs each hold their
  own K/V banks; they gather EAST to one colmux. Instead of all sending at once with a destination
  tag (impossible), exactly ONE PE emits at a time (`pos_emit` = RAMP→EAST) while the rest forward
  (`pos_fwd` = WEST→EAST). A **control wavelet passes the "turn" (baton) EAST**:
  `kv_egress_turn2 = [SWITCH_ADV, SWITCH_ADV]` (`prefill.csl:833`) — with `pop_on_advance`+`ring_mode`
  (set in init, `:1573-1578`), the emitter pops the 1st ADV (self `pos_emit→pos_fwd`), the 2nd
  propagates on the painted W→E route to the EAST neighbour (`pos_fwd→pos_emit`). The chain tail uses
  `kv_egress_turn1 = [SWITCH_ADV]` (`:842`, only self; must be `encode_payload(1,…,true,{})` so ALL 8
  slots stay NOCE and the spent baton is filtered at the colmux's WEST→RAMP, not delivered as data).
  Emitted at `kv_egress_adv` (`:878`) on a `.control=true` fabout DSD (`:817`).
- **The load-bearing reframe: space-multiplex (crossbar, absent) vs time-multiplex (baton, present).**
  The gather is achieved by **time-multiplexing one fixed W→E route** with a stepped switch — no
  wavelet ever says "→ colmux." Same goal as a keyed crossbar (N→1), opposite mechanism.
- **Correctness has no runtime net** (skill: count-exactness, not handshakes): no key, no ack. The
  baton must arrive in the deterministic serpentine order; head/middle use turn2, tail turn1; spent
  batons must keep their NOCE bit. One mis-step = silent corruption/hang (the `enter_request` pos1→pos0
  reset comment / "1xN hang" is exactly guarding this).
- **The ≤4-position limit is *why* a crossbar can't be built from switches** — N-way content selection
  needs N ports; a switch gives 4 sequential positions.
- **Bigger picture — the fabric is a small toolbox of static/choreographed primitives**, each dodging
  keyed routing a different way: switch-stepper baton (KV gather), **rotate-and-match** (ht_head vocab
  LUT), **parity shift chain** (inter-block shuttle), **chain all-reduce** (comm_pe). Common trait:
  destination/selection fixed at compile time; the only runtime "motion" is *who does what on which
  step*. Doing an ML op on WSE = translating it into a composition of these primitives.

## Implications / next actions

- [ ] **NEW SESSION (Le's ask):** discuss this framing in its own right. Candidate angles:
  - How the "no keyed routing / orchestration-primitives" lens **constrains the KV-reuse/tiering
    roadmap** — e.g. does any planned mechanism (reverse prefill↔decode bridge, on-chip keyed store
    placement P3, T1 idle-PE park/reload in M3, off-chip retained pool in M4) implicitly assume
    content routing? If so it must be re-expressed as a static-topology + stepper, or moved to host.
  - Whether the primitive toolbox (baton-gather / rotate-match / parity-shift / chain-reduce) is
    **sufficient** for the tiered-KV movements we need, or a new primitive/host round-trip is required.
  - The **≤4-position + reconfig-cost** limit as a first-class design constraint when scaling gather
    fan-in.
- [ ] On drain: this refines/extends [[csl-control-payload-mechanisms]] (which already has the
  control-wavelet bit layout + SWITCH_ADV mechanics) with the *architectural framing* + a concrete
  worked example; consider folding a distilled version into that topic's evergreen facts (maintain pass).

## Pointers

- Code: `models/qwen3_1p7b-prefill/src/prefill.csl:817` (`.control` DSD), `:826-844` (turn2/turn1 encode),
  `:878` (`kv_egress_adv`), `:108-112` + `:1573-1578` (switch ring_mode/pop_on_advance config).
- Skill: `cerebras-kernel-comm-patterns` (Gate 1: no keyed routing; the ≤4-position stepper; P-4 seam).
- Skill: `cerebras-kernel-algo-walkthrough` + assets `assets/kernel-algo/qwen3_1p7b-prefill.{kv_egress_colmux,ht_head,comm_pe,prefill}.{md,svg}` — the primitives worked out per kernel.
- Related topics: [[csl-control-payload-mechanisms]], [[e2e-kernel-dataflow-and-topology]], [[pr14-real-serving-port-contract]].
