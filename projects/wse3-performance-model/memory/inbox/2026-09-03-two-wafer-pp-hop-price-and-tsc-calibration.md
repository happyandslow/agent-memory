# Two-wafer pipeline-parallel decode on CS-3: the per-hop price is ~175 µs (≈135 µs of it the SDK stream floor), not tens of ms; TSC runs at ~750 MHz — 2026-09-03

**Project:** wse3-performance-model
**Author:** claude
**Status:** captured

## Situation

You are pricing a multi-wafer (layer-pipeline) route for a model that does not
fit one wafer, and the only crossing numbers you have are nc_service's
18–21 ms spec-dec *rounds* — so you are about to write "tens of ms per wafer
boundary". Or you are converting a WSE-3 TSC cycle count to time and reaching
for 0.85 GHz (SDK) or 1.1 GHz (WaferEngine convention). Or you want to know
whether a bigger hidden state changes the hop price.

Doc: `wse3-performance-model/docs/analysis/2026-09-03-4b-two-wafer-pp-decode-demo.md`.
Code + raw: `wse3-performance-model/demo/4b-pp-demo/` (`code/`, `cs3/`, `sim/`,
`tools/`, `PROVENANCE.md`, `README.md`). ContextBase log: see Pointers.
Figure: `artifacts/2026-09-03-two-wafer-pp-floorplan.png` (script beside it).

## What was built (the cut)

- Qwen3-4B decode (`models/qwen3_4b-decode` @ WaferEngine `b136ab64`, frozen
  copy) split A = rows 0–1 = layers 0–17, B = rows 2–3 = layers 18–35 +
  HT_tail; each wafer is a normal 2-row build (`P_Y_BLOCK_NUM=2, n_layers=18`)
  with `PP_LAYER_OFFSET` shifting the per-global-layer weight/KV seeds.
- Only 4 existing files touched: `ht_tail.csl` (`emit_north` guard),
  `demux.csl` (`wait_ready` bypass, optional ingress TSC stamp), `launch.py`
  (role-gated regions + in-pod host loops), `launch_sim.py`. New: `z_mux.csl`
  (1×256 Z gather column → host stream, per-frame TSC stamps), `pp_rdma.py`
  (persistent RC-QP RDMA-Write link, QP info over the TCP control socket,
  `mlx5_0` + RoCE v2 GID auto — nc_service `_RdmaWarmConn` shape, shim +
  `librdmaw.so` copied from nc_service `40ad611`), `launch_device_pp.py`
  (two SdkLauncher sessions = two wsjobs, B's 10.27.x pod IP via `hostname -I`
  injected into A's command), `launch_passthrough.py` (ring bench),
  `tools/check_tokens.py`. HT_head is not needed: the host does the `W_E` row
  copy (bit-identical to the on-chip lookup); the STOP flood traverses the
  split like a normal frame. No WaferEngine tree modified.

## Results (all measured on CS-3, 2026-09-03, SDK 2.10 client / 1.13.2 appliance)

- **Lockstep two-wafer decode, RDMA hop, bsz 1, prefill 4096 / decode 4096,
  same config as the 1,081.7 tok/s baseline:** 1,378.5 ± 4.4 µs/token (n=2,
  spread 0.64 %) = 725 tok/s host-wall; device 1,037,474 / 1,030,896 cyc/token
  → **1.32× (cycles) / 1.33× (host-wall) the single wafer**; **byte-exact
  token/top-K/logit-bit match over 4,096 steps in every run (RDMA ×3, TCP ×1)**.
  TCP hop: 1,401 µs (+18 µs). Negative control (sign-flip two bf16 of one
  relayed frame at step 64): checker fails at step 64. Adding-up gate 99.2 %.
- **Per-token split (host-A clock):** A `send X→recv Z` 614; A→B→A round trip
  738 (= B's `send X` 5.5 + `recv record` 708 + token write 22; wire+wait
  residual **3 µs**); embed 13; enqueue 5.
- **Transport alone (two pods, 5,120 B down / 8 B back):** RDMA-Write RTT
  11.0 µs p50 / 12.0 p99; TCP NODELAY 31.9 / 66.5.
- **SDK stream ring alone (host→demux→z_mux→host, no compute):** RTT
  **≈160 µs flat** for 8 B…10 KB; blocking vs spin receive, `io_buffer_size`
  256/1024/8192, auto vs pinned `io_loc` — none move it. ≈24 µs of it is the
  two 1×256 store-and-forward columns (hop count, not bytes; a 2-lane column
  is 0.1 µs); **≈135 µs is the H2D+D2H completion latency** (same as the
  nc_service June passthrough ring, 0.166 ms). Above 10 KB: 12 KB +7 µs,
  20 KB +11 µs, 40 KB +59 µs (≈1.4–2 µs/KB, p99 widens first).
- **On-wafer residency in the real lockstep (single-PE clock):** wafer A
  X-arrival→Z-exit **488 µs** (p50 488, p99 510) vs 602 µs host bracket ⇒
  **SDK H2D+D2H ≈114 µs per wafer**; residency − 443 µs of 18-layer compute
  ≈ 45 µs (columns + row-0 broadcast + result multicast).
- **Budget:** compute 443+443 + tail 142 ≈ 1,028 (= the single wafer's 1,036)
  + SDK stream ≈250 (two wafers) + columns/fan-out ≈45 + host 19 + wire+wait 14
  = 1,383 µs. **≈70 % of the hop cost is the SDK per-call stream latency;
  the network is 3 %.** Standalone saturated per-wafer period 166 k cyc
  (= one 9-layer row's pipeline period, a throughput floor, not latency).
- **Scaling rule (single request):** T(N) ≈ C_model + ≈170·N µs — each extra
  wafer adds one H2D+D2H ring (+ ≈5 µs wire); the tail→head token return is
  wire-only. For 4B: N=1 1,036 / N=2 1,383 (measured) / N=4 ≈1,730 µs.
  Hidden-state size does not change it for bsz-1 dense models (≤10 KB flat).
- **TSC calibration (closed loop):** device period == loop period ⇒ TSC ≈
  **750 MHz**; "@0.85 GHz" tok/s are ~13 % high (1,081.7 → 965 host-wall),
  "@1.1 GHz" ~47 % high. Report cycles; host-wall is the time cross-check.
- **Corrected reading of nc_service:** its 18–21 ms were per spec-dec round
  (≈14 ms fabric; host+transport ≈3–4 ms dominated by the gateway→worker
  `launcher.run` RPC each round; KV wire 70–82 ms for 128 MB, bandwidth-bound).
  Here there is no control-plane RPC per token; the host loops are the two pod
  workers (same pod-to-pod arrangement as `kv_channel`). No single-host,
  two-wafer mode exists in this stack.

## Gotchas learned

- Cross-PE TSC stamps cannot be aligned by an init-time sync: `enable_tsc` on
  the z_mux column ran ~133 ms after the demux column's, both counters start
  near 0, so a one-shot sync reads ~1 cyc while frame-time differs by ~1e8
  cyc. Stamp both events on ONE PE (z_mux records its own TSC when the ingress
  stamp lands).
- Jobs: bench `pyn62skh…`/`jrm8npup…`; lockstep RDMA `l4byz9vg…`+`pdscrt6w…`,
  repeats `89xqplpe…`+`5pldiajm…`, `unaadmep…`+`jj7nok69…` (stamped); TCP
  `nfok7kru…`+`e9vkqhyk…`; negative `u6j4psvo…`+`e73fridn…`; standalone
  `yxbgtyau…`, `2ky5uzpw…`; rings `3xeenwco…`, `cnzfrgrw…`, `cdya93ms…`.
  Baseline `wsjob-rcbpvpt6cay6aomhuujnx9` (ContextBase K0mf3Dd2WF).

## Implications / next actions

- [ ] Class-P2 per-hop price for the multi-wafer route: ≈170 µs per wafer per
      token at bsz 1, ≈135 of it the SDK stream floor. Below that needs a
      wafer→wafer streamer path the SDK does not expose — ask Cerebras.
- [ ] Host-side stream knobs are exhausted (measured); do not spend more time
      there. Multi-request overlap can hide the hop for throughput (per-row
      period 222 µs) but not for single-request latency; bsz>1 is still
      blocked by two small SRAM buffers (separate capture).
- [ ] Re-label prior "@0.85 GHz" tok/s figures as cycle counts before
      comparing across documents.

## Pointers

- `demo/4b-pp-demo/` (code, provenance, `cs3/` timing JSON + records + token
  gates + `two_wafer_pp_floorplan.png`, `sim/`), analysis doc above.
- Memory artifacts: `projects/wse3-performance-model/artifacts/2026-09-03-two-wafer-pp-floorplan.png`,
  `…/2026-09-03-plot_pp_floorplan.py`.
- Related captures: `2026-09-03-cs3-run-heredoc-hang-and-container-env.md`,
  `2026-09-03-simfab-real-time-stall-detector.md`; nc_service topics
  `m2-device-bringup-and-the-ingress-blocker`, `specdec-d2h-latency`
  (the 0.166 ms passthrough ring), `specdec-modeb-drive-path`.
