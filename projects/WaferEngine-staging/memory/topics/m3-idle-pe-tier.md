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

## Updates — 2026-08-23

Drained `memory/inbox/2026-08-22-m3-payload-sweep-storage-ce-bound.md` into this topic.

- The 256-compute-PE + one-storage-PE `column_cycle_demo` payload sweep on real WSE-3 is deterministic and storage-CE-bound, not wire-bound. Setting: work-repo commit `48467e5` / result commit `facc8c4`, branch `lexu/staging/m3-on-chip-kv-offload-study`, SDK 2.10 client / 1.13.2 cluster, E ∈ {4,32,64,128,256,512,1280} u32 words/PE, n=3 each.
- Timing must start from a host GO wavelet after `runtime.run()`, not from each PE's init task. The rejected init-task method measured ~90 ms of per-PE load skew (device E=32: 91,684 µs vs 614 µs after the fix). Do not time SdkLayout protocols from boot.
- Device result: floor ≈57 µs/cycle; for E ≥ 32, full cycle is linear at **20.247 µs per word-per-PE**, split into serial park and emit phases (~10.01 + 10.24 µs). Representative points: E=4 → 57.4 µs, E=32 → 614.3 µs, E=512 → 10,333.0 µs, E=1280 → 25,882.9 µs.
- The pre-registered wire-bound model (0.524 µs/word from 2×1024 B over a 3.91 GB/s edge) is refuted by 39×. The located mechanism is storage-side CE per-wavelet work: ~43 cycles per park wavelet plus ~44 cycles per reload wavelet. The derived ~101 MB/s per-column number is as-built cycle throughput, **not** a link bandwidth measurement; keep link bandwidth as a separate, still-needed model input.
- Model form at lpb=4: `t_cycle(L) ≈ 57 µs + 1.265 µs × L`. In free-decode-token units (654.95 µs/token), L=512 costs ~0.94 token, L=2048 ~3.9, L=8192 ~15.8, and L=20480 ~39.5. Next lever is a storage-side DSD bulk-receive / DSD block-emit variant to remove per-wavelet CE involvement.

## Updates — 2026-08-24

Drained two 2026-08-23..24 M3 performance/model captures into this topic.

- Clock convention for this M3 path is **0.85 GHz** (Le, 2026-08-23); raw device cycles are authoritative. Earlier <=2026-08-22 JSON µs used 1.1 GHz and must be multiplied by 1.294 to re-express at 0.85 GHz. `bench/layer_block/utils.py` still carrying `FREQ_GHZ=1.1` is a known in-repo convention conflict, not silently unified.
- The as-built single-row model is pinned: `t_full(N,E,D) = c_floor_per_row*N + c_floor_const + (E-4)*N*c_word_roundtrip + 2*(D-1)*t_hop_router`, with `c_park_storage=43.3 cyc/word`, `c_word_roundtrip=86.3 cyc/word`, `c_floor_per_row=245.4 cyc`, `c_floor_const=326 cyc`, `t_hop_router=2.0 cyc/hop`. The bottleneck is CE per-wavelet work, not wire bandwidth.
- Exp-B owner-side bulk fabin-DSD receive proved owner data-task consumption was the reload bottleneck: full-cycle marginal improved from 86.87 to 56.00 cyc/word, park stayed 43.00, and reload fell from ~43.9 to 13.00 cyc/word (storage emit loop). Do not treat a backpressure-coupled span as a stage cost.
- Multi-row v4/v5 verdict: v4 GO-chain and v5 cascade both fit a forwarded-word law over `fwd_words=(N-N/R)*E`, but the coefficient exposes the mechanism. v4 is router-priced (`~1.06 task / 1.29 dsd cyc/word`); v5 is CE store-and-forward (`30.7 / 47.0 cyc/word` plus a ~157k-cycle DSD constant for R>1). v3/v5 win the single-row degenerate case, but v4 wins for all `R >= 2`; a hybrid with v4 router transit and v5 static compute column would dominate both.
- Durable design lessons: always measure each implementation's own R=1/degenerate baseline; CE-touch vs router-touch is the 30-75 cyc/word vs ~1-2 cyc/word dichotomy on WSE-3; preregistered bands are useful when falsified; and DSD can expose serialization that task-mode backpressure hides.

Next as-built rungs: storage-side DSD emit, storage-side DSD park receive, and/or a hybrid multi-row design that keeps v4's router-priced transit without v4's high R=1 role-machinery premium.
