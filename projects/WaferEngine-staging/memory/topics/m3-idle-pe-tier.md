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

## Updates — 2026-08-23 (later)

Drained `memory/inbox/2026-08-23-m3-perf-model-coefficients.md` into this topic.

- **Clock convention: 0.85 GHz (Le, 2026-08-23)** for this path; device CYCLES are authoritative everywhere. µs in results dated ≤2026-08-22 used 1.1 GHz (×1.294 to re-express). Free-token ratios are cycles-to-cycles against the 720,445-cyc decode anchor, hence clock-free. Known unresolved conflict: `bench/layer_block/utils.py` still carries 1.1.
- Single-row model is DEVICE-FIT (15 anchors, ≤0.89%): `t = (245.4·N + 326) + (E−4)·N·c_word_roundtrip + 2(D−1)·2.0`. Coefficients: `c_park_storage=43.3` cyc/word (Exp-A P1, −0.7% uniform over N∈{32..256}), `c_word_roundtrip=86.3` (∝N to 0.03%, Exp-A P2), floor linear (Exp-A P3, resid 8.8 ns), `t_hop_router=2.0` cyc/hop with **no per-word term** (Exp-C) ⇒ storage placement is latency-free.
- The cycle composes as a **pipeline (max of stage costs), not a sum**: park span alone equals `c_park_storage·N·E` within 1% at every N — no room for additive wire/receiver terms. Never take a backpressure-coupled span as a stage cost (Exp-C's shrinking emit span was the tell).
- **Exp-B verdict**: owner-side data task WAS the reload bottleneck. Owner bulk fabin-DSD receive drops the roundtrip marginal 86.87→56.00 cyc/word; park stays exactly 43.0 in both modes (clean control); reload share falls 43.9→13.0 = the storage `@mov32` emit loop. New semantics: a microthread-claimed input queue delivers **no control-task activations** (router `SWITCH_ADV` still executes; only the CE tap vanishes) — dsd mode suppresses TURN taps and drops the fence.
- Pointers: `column_cycle_demo/perf_model.py`, `results/PREREGISTRATION-exp{AC,B}.md`, ContextBase 📐 "M3 park/reload as-built performance model" page.

## Updates — 2026-08-24

Drained `memory/inbox/2026-08-24-m3-multirow-v4-v5-device-comparison.md` into this topic.

- Two multi-row designs built and **both device-measured** (81 runs total, 45 v5 + 36 v4, every cell n=3 with 0-cycle spread, zero infra failures). v4 GO-chain: R sequential epochs, roles reprogrammed at GO taps via **direct switch-position byte writes** (byte = in_sel<<5|out_bits; S→RAMP=0x50, S→N=0x48; pos1=reg0[7:0], pos2/3=reg1[7:0]/[15:8]) — the tile_config `set_rxtx_switch_pos` library writes the wrong tx bit for RAMP (register-dump proven). First v4 silicon 2026-08-23: GO chain + role reprogramming + byte writes all work at 256 PEs. v5 cascade: compute column byte-identical to v3; strip-internal static hop colors; STRIP_TAIL causal end-of-stream; row 0 synthesizes TURNs/fence.
- **Same law, two coefficients**: both designs' multi-row delta vs their OWN R=1 is linear in `fwd_words=(N−N/R)·E`; tax_v4 = 1.06/1.29 cyc/word (router transit) vs tax_v5 = 30.7/47.0 (CE store-and-forward, +157k dsd-R>1 strip-serialization const) — 25–35× apart. Each design pays an always-on R=1 premium over v3: v4 +9.6 cyc/word (role machinery), v5 +1.6 (cascade branches). **Crossover: v3/v5 win single-row; v4 wins all R≥2** (dsd E=512 R=4: 30% faster).
- Durable rules extracted: (1) every implementation carries its own degenerate-case baseline — never diff against another implementation's anchors (H1 falsified at +0.7–2.3%); (2) the CE-touch vs router-touch dichotomy is ~13–75 vs ~1–2 cyc/word, measured four independent ways — the design rule for on-chip transfer mechanisms; (3) the 25–35× tax gap IS a CE-allocation decision (v5 concentrates all forwarding on row-0's CE; v4 spreads endpoint work per row and leaves movement to routers); (4) dsd exposes serialization task mode hides (strip own-emit-before-relay ⇒ the 157k const).
- **Tier verdict**: on-chip reload share is 13.0 cyc/word ⇒ 0.06–2.0 ms for H=256–8192 — 46–170× below host ingress I(H); resume becomes Δ-dominated (Δ = L_new's forced-decode, lane-independent, E10-cancellation-verified). Swap ≈ L/692 token-equivalents as-built; projected L/~3000 after storage-side DSD (projection). Tiering: T0 in-PE resident → T1 on-chip strip → T2a recompute (tiny/un-parked) → T2b DRAM (overflow). Open: hybrid (v4 router transit + v5 static compute column) would dominate both; unmeasured: concurrent-decode interference, round-gap fit, large-L prefill curve.
- Three-way anchor row (task E=64, cycles): v3 1,388,470 · v4 1,535,920/1,544,946/1,550,855 (R=1/2/4) · v5 1,420,244/1,675,327/1,812,526. All 39 anchors + three predictors in `column_cycle_demo_multirow_v5/perf_model.py` (selftest v3 0.89% / v5 0.83% / v4 0.23%).
- Pointers: `PREREGISTRATION-multirow.md` (predictions + verdicts + consolidated record), `meetings/2026-08-24-src/REPORT.md` (fullest summary incl. slides map + transport-vs-CE decomposition), v4 result meta commit "2ffe1f6" = placeholder for b03bd6c.

## Updates — 2026-08-24 (fine-grained coefficient interpretation)

- The v4 multi-row coefficients `C_router=1.06` (task) and `1.29` (owner DSD) cycles per forwarded word do **not** represent two physical router speeds. Both modes use the same router-only transit path. They are end-to-end fitted taxes under different endpoint consumption, backpressure, and timing regimes; the small difference must not be attributed to router hardware changing with DSD.
- The v5 reload-relay coefficient `c_relay_word≈28.8` cycles/word is an **absolute relay-stage coefficient**, not an increment on top of the local emit loop. In the implementation, an incoming word lands in an IQ and activates `relay_in(word)`, which performs one `@mov32(up_out, word)` and returns. By contrast, the `13.0` cycles/word local emit path executes many `@mov32` operations in one tight CE invocation. The model therefore reads approximately `28.8 = 13.0 emit + 15.8 fabin landing / per-word task dispatch / bookkeeping / reinjection`. Evidence grade: `13.0` was isolated by the owner-DSD experiment; `28.8` was decomposed from `tax_dsd=(c_fwd-44.2)+(c_relay-13.0)` and cross-checked against task mode to 1.6%, not timed as an isolated TSC span.
- The v4 `C_owner` reduction `96.00→65.08` cycles/payload-word is primarily a **granularity change**, not a copy-elimination result. Task mode invokes `reload_data(word)` for every arriving wavelet and performs tag/sequence branches plus ledger updates on that per-word path. Owner-DSD mode performs one bulk `fabin_dsd→reload_buf` transfer, activates one completion task, and then scans the local buffer. It therefore still writes and later reads a local buffer; the measured `30.92` cycles/word saving comes mainly from replacing per-wavelet CE task dispatch/control work with a bulk microthread transfer. `C_owner` is an ordinary endpoint full-cycle marginal coefficient, not a pure receive-only microbenchmark, so the fit does not support a more detailed numerical split.
- Design consequence: preserve router-only transit whenever possible, batch CE endpoints with bulk DSDs, and label inferred stage decompositions separately from directly isolated TSC measurements.
- Code pointers: `column_cycle_demo_multirow_v5/src/strip.csl::maybe_start_upload` and `relay_in`; `column_cycle_demo_multirow_v4/src/compute.csl::reload_data`, `reload_dsd_done`, and `enter_participant`; fitted constants in `column_cycle_demo_multirow_v5/perf_model.py`.

## Updates — 2026-08-24 (committed artifact/version manifest)

Use this manifest when a future reader needs to reproduce a number or locate the exact code and raw CS-3 evidence. Repository: `git@github.com:happyandslow/WaferEngine.git`. Study branch: `lexu/staging/m3-on-chip-kv-offload-study`. Audited branch snapshot and matching remote head: `255dab72c4231f85c28a82007bf4c2830696537d`. Required base is an ancestor at `lexu/staging/kv-feature@77d6d407328f46314c90238d799f9ed5402d55b6` (the merge base is exactly that commit).

| artifact | committed location | device/source identity | committed record available from the audited head |
|---|---|---|---|
| v3 single-row protocol and Exp-A/C | `models/qwen3_1p7b-decode/bench/m3_park_band/column_cycle_demo/` | payload/Exp-A/C baseline cited as `48467e5`; cycle-model consolidation `e9e6ec8ee14435d753e09b826d8f6eb8dd250abc` | `results/2026-08-22-payload-sweep/` (21 raw JSONs), `results/expAC/` (30 raw JSONs), `results/PREREGISTRATION-expAC.md` |
| v3 Exp-B owner DSD | same v3 directory | as-run source/preregistration `fd949861b17cc483cabbbe526cdc31ca05f26a8d`; result/verdict commit `676c7aa849ab7a5b94819551b257fa61a984435f` | `results/expB/` (12 raw JSONs) and `results/PREREGISTRATION-expB.md` |
| v4 multi-row GO-chain | `.../column_cycle_demo_multirow_v4/` | true as-run source `b03bd6c897ef38a7239d2533a91316bea0f3a5d6`; result/model packaging `4e2d2e2eb00bf497ce9e9aff0a659e8f16267002` | `results/2026-08-23-v4-matrix/` (36 run JSONs plus `SUMMARY.json`) |
| v5 multi-row cascade | `.../column_cycle_demo_multirow_v5/` | as-run driver/source `c50b94bc644a611708bcb1f45b5d95335c5a778f`; raw-result/verdict commit `60737f5a3d2e2521e8d7c58e54c066b1594a6466` | `results/2026-08-23-multirow/` (45 run JSONs plus `SUMMARY.json`) |
| canonical multi-row record | `.../column_cycle_demo_multirow_v5/results/PREREGISTRATION-multirow.md` | consolidated at `63b89ac1a80c06226b9c4a8b88f2e0883dc1e934` | predictions, post-run verdicts, settings, raw-cycle tables, fit provenance, v4 correction |
| three-design performance model | `.../column_cycle_demo_multirow_v5/perf_model.py` | latest model commit `4e2d2e2eb00bf497ce9e9aff0a659e8f16267002` | `--selftest` covers 39 device anchors: v3/v5/v4 max error 0.89%/0.83%/0.23% |
| editable v4-v5 topology | `docs/diagrams/m3-multirow-v4-vs-v5.excalidraw` plus PNG/SVG | `4f41a596465290bc3a113bf3b776b32abb174576` | current study head also includes committed GO-chain coverage diagrams through `255dab72...` |

Stable entry points: [audited repository snapshot](https://github.com/happyandslow/WaferEngine/tree/255dab72c4231f85c28a82007bf4c2830696537d), [canonical multi-row record](https://github.com/happyandslow/WaferEngine/blob/63b89ac1a80c06226b9c4a8b88f2e0883dc1e934/models/qwen3_1p7b-decode/bench/m3_park_band/column_cycle_demo_multirow_v5/results/PREREGISTRATION-multirow.md), [v4 raw matrix](https://github.com/happyandslow/WaferEngine/tree/4e2d2e2eb00bf497ce9e9aff0a659e8f16267002/models/qwen3_1p7b-decode/bench/m3_park_band/column_cycle_demo_multirow_v4/results/2026-08-23-v4-matrix), [v5 raw matrix](https://github.com/happyandslow/WaferEngine/tree/60737f5a3d2e2521e8d7c58e54c066b1594a6466/models/qwen3_1p7b-decode/bench/m3_park_band/column_cycle_demo_multirow_v5/results/2026-08-23-multirow), and [fitted model](https://github.com/happyandslow/WaferEngine/blob/4e2d2e2eb00bf497ce9e9aff0a659e8f16267002/models/qwen3_1p7b-decode/bench/m3_park_band/column_cycle_demo_multirow_v5/perf_model.py).

Traceability rules: raw JSON `wsjob` identifiers, raw TSC cycles, settings, and source MD5s remain the primary per-run evidence. The v4 JSON field `git_commit="2ffe1f6"` is a known placeholder and must be overridden by the true as-run source `b03bd6c897ef38a7239d2533a91316bea0f3a5d6`; the in-file MD5s provide the secondary identity check. All listed source/result commits were verified as ancestors of the audited branch head, and all canonical paths were verified present in that Git tree.
