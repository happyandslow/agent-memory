---
summary: M3 idle-PE/on-chip KV offload tier design notes, including Mode-L park/reload tail-marker route transition, NO_POP broadcast switch waves, and column_cycle_demo evidence.
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

## Updates — 2026-08-22

Drained `memory/inbox/2026-08-21-m3-column-cycle-demo-v3-sim-proven.md` into this topic. It supersedes the segmented-relay parts of the 2026-08-20 Mode-L transition note.

- A single `SWITCH_ADV` control wavelet sent with NO_POP advances every advance-capable PE it passes; routed-then-advance semantics let the wavelet survive to the end of the path. Therefore the 8-command control-payload limit constrains targeted pop chains only, not broadcast switch sweeps; 16-PE and 256-PE columns use the same one-wavelet sweep. `popfalse_probe` verified this on both simfab and physical CS-3 with field-identical ledgers.
- The v2 per-PE park TURN was dropped because pop mode is per-PE-per-color state, not a wavelet attribute. A single column cannot simultaneously use POP_ON_ADVANCE for sender-local TURN death and NO_POP for a column-wide sweep, and the CE cannot safely time a mode switch between phases.
- v3 release protocol: after `@queue_flush` drains the payload, each regular PE directly rewrites its route with `set_config` (`RAMP→S` to `N→S`). Opening the north door is the release action, so no in-flight traffic can race the rewrite. Reload retains per-owner demux TURNs (pop=true, terminated by RAMP-only routing) plus a zero-command FENCE that only P0 catches as the end-to-end drain proof.
- `column_cycle_demo` is now DEVICE-PROVEN at decode block height: real CS-3 job `wsjob-frfycsmtzugnjjoitj5jjp`, `--n-pes 256 --payload-len 64`, strict checker green for 16,384 park words in exact 255..0 order, dual-predicate join, 256-owner reload demux with TURN-arg cross-checks, FENCE at P0 only, ledger gather in exact baton order, and `unexpected=0`. This is functional evidence only, not a performance claim.
- Assumption A1 is now explicit and doc-checked: the door-open rewrite relies on OQ-empty implying payloads cannot be overtaken by newly admitted northern wavelets inside the router. SDK docs only guarantee the queue is empty, not router-internal no-overtake. The storage exact-order automaton is the standing falsifier and passed at 16/10 PE sim and 256-PE device.
- The storage-side `@queue_flush` callback non-firing from wavelet-task context contradicts documented semantics, including the already-empty case. Root cause remains open; do not build protocol correctness on wavelet-task-context `queue_flush` callbacks without re-verifying.
- Payload sizing equation for qwen3_1p7b decode, serve 2x4, P=256, kv_dim=1024 (`kv_cols=4` fp16/PE): per compute PE `S_PE(L)=lpb·ceil(L/256)·16 B`; per column/storage PE `S_col(L)=16·L·lpb B`; demo words `E=4·lpb·ceil(L/256)`. Cross-check: Σblocks `4096·lpb = 114,688 B/token`; `S_col(672, lpb=4)=43,008 B`, matching the ~42 KiB/PE storage-strip budget.

Next gates: run payload-size variation on the demo to measure round-boundary offload/reload overhead vs `E`, then integrate round-boundary reset/re-arm and release semantics into decode round boundaries. Keep `read_symbol` simulator-only and avoid zero-host-stream `SdkLayout` layouts on the appliance.
