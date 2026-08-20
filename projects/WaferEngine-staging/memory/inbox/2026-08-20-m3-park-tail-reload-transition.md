# M3 Mode-L park-tail route transition — 2026-08-20

**Project:** WaferEngine-staging
**Author:** codex
**Status:** captured

## What happened / finding

- Corrected the first Mode-L route-transition fence: Storage must not originate a northbound reload-prepare sweep after park. Park flows north-to-south, so the farthest/northernmost and last source appends `PARK_TAIL` after its final payload on the same switched color, queue, and path.
- Ordered source baton plus same-stream ordering makes `PARK_TAIL` trail every park payload. The marker passes southbound and changes each router from `R_park` to `R_reload` only after crossing it. Storage may start northbound reload only after observing both the exact static payload count and `PARK_TAIL`.
- Storage appends a separate northbound `RELOAD_TAIL` after all reload payloads. It restores `R_Y` hop by hop; next-round compute remains gated by local `route_ready && kv_ready`. No global GO is part of the preferred protocol.
- A control payload carries at most eight switch commands, so long columns require segmented relay. In the 12-PE example, southbound `PARK_TAIL` uses P11..P4 then a CE relay at P4 for P3..P0; northbound `RELOAD_TAIL` uses P0..P7 then a CE relay at P7 for P8..P11.
- Same-color CE receive/reinjection without self-feedback remains an unproven compile/device gate. A precompiled parity pair is the fallback; explicit ACK/GO is retained only if both segmented variants fail.
- This is a protocol candidate only. There is no real-CS-3 ordering or performance evidence yet.

## Implications / next actions

- [ ] Compile-prove the bounded control segments, CE landing, same-color reinjection, and route states.
- [ ] Run adversarial real-CS-3 ordering smokes for both `PARK_TAIL` and `RELOAD_TAIL` before any E1 performance sweep.
- [ ] Keep live decode color/IQ/OQ selection symbolic until the Phase-B resource audit closes it.

## Pointers

- `docs/analysis/m3-on-chip-kv-offload-study.md`
- `docs/diagrams/m3-mode-l-segmented-park-reload.excalidraw`
- `milestones/M3-idle-pe-tier.md`
