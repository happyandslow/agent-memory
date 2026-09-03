# Two-wafer pipeline-parallel decode on CS-3: the per-hop price is ~175 µs, not tens of ms; TSC runs at ~750 MHz — 2026-09-03

**Project:** wse3-performance-model
**Author:** claude
**Status:** captured

## Situation

You are pricing a multi-wafer (layer-pipeline) route for a model that does not
fit one wafer, and the only crossing numbers you have are nc_service's
20–30 ms spec-dec rounds — so you are about to write "tens of ms per wafer
boundary". Or you are converting a WSE-3 TSC cycle count to time and reaching
for 0.85 GHz (SDK) or 1.1 GHz (WaferEngine convention). Doc:
`wse3-performance-model/docs/analysis/2026-09-03-4b-two-wafer-pp-decode-demo.md`;
code + raw under `demo/4b-pp-demo/`.

## What happened / finding

- **Measured (two CS-3s, bsz 1, prefill 4096 / decode 4096, mock weights,
  same config as the 1,081.7 tok/s single-wafer baseline):** Qwen3-4B decode
  split A = layers 0–17, B = layers 18–35 + lm_head/sampling, hidden state
  relayed wafer→host→RDMA→host→wafer every token, runs at **1,378.5 µs/token
  (n = 2, spread 0.64 %) = 725 tok/s host-wall, ≈1.034 M cyc/token** —
  **1.32× (cycles) / 1.33× (host-wall) the single wafer**, token sequence
  byte-exact over 4,096 steps in every run. The "20–50×, host-dominated"
  hypothesis is falsified.
- **Per-token split (host-A clock, adds to 99.2 % of the loop):** A segment
  (H2D → 18 layers → z_mux gather → D2H) 614 µs; B segment 708 µs (incl.
  lm_head + sampling + mux D2H); wire+wait residual **3 µs**; embed row copy
  13 µs; enqueue 5 µs. Two-hop crossing overhead vs single wafer ≈ **350 µs
  per token ≈ 175 µs per hop**, essentially all device↔host stream path +
  the serial 1×256 host-facing fan-out/gather columns.
- **Transport alone (2,000 ping-pongs, 5,120 B down / 8 B back):** persistent
  RC-QP RDMA-Write on `mlx5_0`, RoCE v2 GID idx 5, busy-poll → **11.0 µs RTT
  p50 / 12.0 p99**; TCP NODELAY on the 10.27.x underlay → 31.9 / 66.5 µs.
  Swapping RDMA for TCP in the lockstep moves the loop by only ~18 µs.
- **Why nc_service saw 20 ms and this sees 0.35 ms:** the crossing here never
  touches SdkLauncher → gRPC → appliance-worker serde; both host loops run
  in-pod (`cs_python launch.py`, direct `SdkRuntime` streams,
  `memcpy_required=False`) and talk over a warm QP. The expensive thing was
  the control-plane hop, not the wafer boundary.
- **TSC calibration (measured, closed loop):** in lockstep the device period
  must equal the host loop period; 1,037,474 cyc ↔ 1,382.9 µs gives
  **≈ 750 MHz** effective TSC rate. The single-wafer baseline shows the same
  host/device ratio (1,036 µs host vs 924 µs "@0.85 GHz" = 1.12). So tok/s
  labelled "@0.85 GHz" are ~13 % high (1,081.7 → 965 host-wall) and "@1.1 GHz"
  ~47 % high. Report cycles; use host-wall as the time cross-check.
- Standalone saturated (frames queued 4 deep, no hop): each 2-row wafer's
  period is ~166 k cyc = one block row's (9-layer) pipeline period — a
  throughput floor, not the 18-layer latency a token pays in lockstep.

## Implications / next actions

- [ ] Class-P2 per-hop price for the multi-wafer route: ≈ 175 µs per wafer
      boundary per token at 5 KB (≈ 5 µs of it wire). N-wafer layer PP at bsz 1
      adds ≈ 175·(N−1) µs/token over compute with the current in-pod stack.
- [ ] The remaining hop cost is the D2H/H2D stream path + on-chip 1×256
      gather/fan-out columns — the optimisation target if the hop matters.
- [ ] Re-label prior "@0.85 GHz" tok/s figures in this project as cycle counts
      (or ×0.88) before comparing across documents.

## Pointers

- `demo/4b-pp-demo/` (code, `PROVENANCE.md`, `cs3/` raw timing JSON + records
  + token gates, `sim/`); jobs: lockstep RDMA `wsjob-l4byz9vgzzxcntwfl6qocz`
  + `wsjob-pdscrt6wd4vwehcv7muxoz`, repeat `wsjob-89xqplpez9ktkf2tkbrfgl` +
  `wsjob-5pldiajmspzypeewnlquce`, TCP `wsjob-nfok7kruuk8jssfv8o345l` +
  `wsjob-e9vkqhykdb7gih7fduc2vp`, transport bench `wsjob-pyn62skh9ikgv8g2uyull7`
  + `wsjob-jrm8npupnxw2j5pwuunnvm`.
- Baseline: ContextBase K0mf3Dd2WF, `wsjob-rcbpvpt6cay6aomhuujnx9`.
- Related: nc_service topics `m2-device-bringup-and-the-ingress-blocker`,
  `specdec-modeb-drive-path` (the 20 ms rounds this corrects the reading of).
