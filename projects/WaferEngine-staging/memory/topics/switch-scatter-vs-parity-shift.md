---
summary: Switch gather/scatter versus parity shift for KV distribution — 2026-08-02
tags: [WaferEngine-staging, drained-inbox, 2026-08-02]
---

# Switch gather/scatter versus parity shift for KV distribution — 2026-08-02

This topic was created by the 2026-08-03 maintain pass from a dated inbox capture. Keep it as the durable, topic-scoped home for the finding; the original capture is marked drained.

## Drained capture — 2026-08-02

Source: `memory/inbox/2026-08-02-switch-scatter-vs-parity-shift.md`

# Switch gather/scatter versus parity shift for KV distribution — 2026-08-02

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured

## What happened / finding

- Situation: when distributing one ordered KV payload across a long PE chain, it is easy to treat router-switch scatter and a two-color shift as interchangeable, assume both use the same sender order, or attribute parity to a false rule that one color must use the same route on adjacent PEs.
- A color may be painted differently per PE. Parity is needed because a static store-and-forward PE must terminate its receive color at RAMP and inject the forwarded tile onto the next hop. Alternating `A->B` / `B->A` separates those roles and prevents the router from feeding or duplicating its own input.
- Switch scatter separates the roles in time on one switch-capable color. Each PE starts at `TAKE` (`chain input -> RAMP`); after its complete destination batch, `SWITCH_ADV` selects the pre-painted `FORWARD` position (`chain input -> chain output`). This advances once per batch, not per wavelet, and is not runtime route repainting or keyed routing.
- Switch gather is the reverse ownership protocol: a PE first forwards the upstream batch, then changes to `RAMP -> chain output` when it owns the emit turn. Transit payload stays in the router rather than entering PE memory.
- For `source(WEST) -> PE0 -> PE1 -> PE2 -> PE3`, with `PEi <- di`, switch scatter sends nearest-to-farthest: `d0, ADV, d1, ADV, d2, ADV, d3`. A parity shift sends farthest-to-nearest: `d3,d2,d1,d0`; PE0 receives all, forwards the first three, and keeps the last. The sender orders are opposite for the same injection side and target mapping.
- Current standalone decode enters each block from the EAST and shifts WEST, so host column order `d0,d1,...` (WEST-to-EAST coordinates) is still farthest-to-nearest relative to the EAST entry. The east-most column receives all tiles and keeps the last.
- Switch does not reduce hop-distance traffic. It removes transit CE work and fabric-to-memory-to-fabric copies. Its costs are switch-capable colors, exact ordered batches, control wavelets, and whole-chain reset/re-arm.
- A parity shift is preferable when the same route repeats many independent phases, local processing is required, switch resources are scarce, or one-tile staging is cheap. It is stateless across phases: metadata and every layer's K/V phase can reuse the same receive/forward counts without resetting router switches.
- A switch is preferable when each target owns one contiguous large batch, each PE changes role once per round, and transit staging/CE forwarding is the scaling issue.
- WaferEngine standalone decode intentionally composes both: switch scatter across Y rows for one large per-row bundle, then a two-color parity west-shift across X columns for the repeated metadata and per-layer K/V phases.
- This is recurring procedural knowledge and has been promoted, with user approval, to `/home/lexu/claude-skills/cerebras-switch-vs-parity-shift/`.

## Implications / next actions

- [ ] During the next agent-memory maintain pass, fold this into the existing communication-pattern material rather than creating a duplicate topic.
- [ ] Before replacing a parity shift with a switch, prove that payloads can be batched once per target and account for reset cost between every repeated phase.
- [ ] Before comparing sender order, state the injection side and label targets by distance from that side; coordinate order alone is ambiguous.

## Pointers

- `models/qwen3_1p7b-decode/src/kv_ingress_adaptor.csl`
- `models/qwen3_1p7b-decode/src/kv_ingress_injector.csl`
- `models/qwen3_1p7b-decode/src/decode.csl` (`kv_ingress_meta_phase`, `kv_ingress_layer_phase`, `kv_ingress`)
- `models/qwen3_1p7b-decode/launch.py` (KV ingress route painting, `_repack_kv_band`)
- `models/qwen3_1p7b-prefill/src/prefill.csl` (KV switch gather)
- `cerebras-kernel-comm-patterns/references/patterns.md` (P-4/P-5)
- `cerebras-kernel-comm-patterns/references/glue-idioms.md` (G-1/G-14 and invariants I1-I6)
