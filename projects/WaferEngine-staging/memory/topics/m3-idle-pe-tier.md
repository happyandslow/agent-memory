---
summary: M3 idle-PE/on-chip KV offload tier design notes, including Mode-L park/reload tail-marker route transition and same-color segmented control gates.
tags: [waferengine-staging, qwen3, kv-cache, idle-pe, m3, routing, csl]
---

# M3 idle-PE tier

## Why this exists

This topic tracks the M3 / idle-PE tier for on-chip KV offload and reload, distinct from host-DRAM reload and in-place retain. Use the project plan and `milestones/M3-idle-pe-tier.md` as roadmap/source material; this note preserves durable protocol facts and gotchas.

## Updates — 2026-08-21

Drained `memory/inbox/2026-08-20-m3-park-tail-reload-transition.md` into this topic.

- Corrected the first Mode-L route-transition fence: Storage must not originate a northbound reload-prepare sweep after park. Park flows north-to-south, so the farthest/northernmost and last source appends `PARK_TAIL` after its final payload on the same switched color, queue, and path.
- Ordered source baton plus same-stream ordering makes `PARK_TAIL` trail every park payload. The marker passes southbound and changes each router from `R_park` to `R_reload` only after crossing it. Storage may start northbound reload only after observing both the exact static payload count and `PARK_TAIL`.
- Storage appends a separate northbound `RELOAD_TAIL` after all reload payloads. It restores `R_Y` hop by hop; next-round compute remains gated by local `route_ready && kv_ready`. No global GO is part of the preferred protocol.
- A control payload carries at most eight switch commands, so long columns require segmented relay. In the 12-PE example, southbound `PARK_TAIL` uses P11..P4 then a CE relay at P4 for P3..P0; northbound `RELOAD_TAIL` uses P0..P7 then a CE relay at P7 for P8..P11.
- Same-color CE receive/reinjection without self-feedback remains an unproven compile/device gate. A precompiled parity pair is the fallback; explicit ACK/GO is retained only if both segmented variants fail.
- This is a protocol candidate only. There is no real-CS-3 ordering or performance evidence yet.

Next gates: compile-prove bounded control segments, CE landing, same-color reinjection, and route states; run adversarial real-CS-3 ordering smokes for both `PARK_TAIL` and `RELOAD_TAIL`; keep live decode color/IQ/OQ selection symbolic until the Phase-B resource audit closes it.

Pointers: `docs/analysis/m3-on-chip-kv-offload-study.md`, `docs/diagrams/m3-mode-l-segmented-park-reload.excalidraw`, `milestones/M3-idle-pe-tier.md`.
