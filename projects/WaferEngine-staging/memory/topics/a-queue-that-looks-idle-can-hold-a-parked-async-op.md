---
summary: A queue that looks idle between phases can be holding a parked async op — 2026-07-31
tags: [WaferEngine-staging, drained-inbox, 2026-07-31]
---

# A queue that looks idle between phases can be holding a parked async op — 2026-07-31

This topic was created by the 2026-08-03 maintain pass from a dated inbox capture. Keep it as the durable, topic-scoped home for the finding; the original capture is marked drained.

## Drained capture — 2026-07-31

Source: `memory/inbox/2026-07-31-a-queue-that-looks-idle-can-hold-a-parked-async-op.md`

# A queue that looks idle between phases can be holding a parked async op — 2026-07-31

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured

## Situation this applies to

You want to add a second data path to an existing CSL region and you are deciding whether to
reuse its colors/queues. The two paths are **time-disjoint** — yours runs at the end of a round,
the existing one at the start — so sharing looks free. You count bound queues, see headroom, and
conclude the resource is idle in between.

## Finding

**Time-disjoint is not the same as quiescent.** On the decode KV-ingress staircase
(`kv_ingress_injector.csl`, `kv_ingress_adaptor.csl`), `peel_meta0` leaves an **outstanding async
fabin `@mov32` parked on IQ2 for the whole decode phase** (`injector:80-82`, `adaptor:93-95`).
The queue is not free between phases — it holds a live blocked operation. Aliasing it would be a
correctness bug that no headroom count reveals.

Output queues on the same PEs *are* genuinely quiescent between rounds, so the hazard is
asymmetric: **input side unsafe, output side safe.** With 12–13 of 16 queues free on those PEs
there was no reason to share either way.

## Second-order finding: where the phase guarantee actually lives

The staircase PEs have **no device barrier** — `adaptor:136-153 rearm()` re-arms for round N+1 the
moment round N's ingress finishes (~46 ms into a round that lasts N×655 µs), then idles. What
actually keeps round N+1's ingress out of round N's tail is the **host's sequential round loop**
(`launch_decode.py:2746`). ⇒ The phase separation is a **host-side convention that must be
stated and enforced**, not a device-enforced property you can lean on.

## Check before assuming a resource is shareable

1. Is there an outstanding async op parked on it across the gap?
2. Is the phase boundary enforced by the device, or only by the host driver?
3. Are the free switch positions on the color actually usable, or is the position sequence driven
   by a fixed `SWITCH_ADV` count that extra positions would desync? (Here: `in_color` had pos2/3
   free but the adaptor issues exactly `num_rows-1` advances — adding a position breaks it.)

## Pointers

- `topics/s3b-decode-kv-egress-options.md` (the design this audit feeds)
- audit was by direct source reading, **not** the `csl-color-audit` skill — that skill reads a git
  ref and cannot resolve SdkLayout auto-allocated color ids either
