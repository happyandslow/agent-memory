# Real verify-model deployment — where it lives (for the EIDF sicheng bring-up)

Date: 2026-07-14. Q: "how is the REAL verify model deployed?" (CS-3 down → mock draft).
Answer: there are TWO distinct "real verify" surfaces; don't conflate them.

## 1. nc_service DraftControl **gRPC** verifier (the transport contract)
- Live real verifier at **`10.22.28.100:32245`** on EIDF — TCP-OPEN and reachable
  from the sicheng box (10.24.7.82, internal 10.1.0.215). Validated 2026-06-29
  (see topic `specdec-d2h-latency.md`): driver_main --appliance real --addr
  10.22.28.100:32245, 1000 rounds, 0 err, verify-side p50 3.296ms.
- Our Rust **mock draft** (draft_service DIRECT) DID open the gRPC stream + send
  hello to it, but got **0 DraftAdvance commands back** in 40s. The Rust
  verify_service auto-drives a benchmark on registration; the REAL server does
  NOT — it waits for a real prompt-initiated session (cf. ContextBase doc
  "SpecDec verify↔draft protocol: prefill vs decode", SEOAxhYoeW). So "mock draft
  vs real gRPC verifier" ≠ auto-benchmark; needs a session trigger.

## 2. The REAL MODEL = **Kimi K2.5 TP=8 SGLang verify server** (actual weights)
- Deployment report: ContextBase **"Report — cu12 Full-Server Enablement + Kimi
  K2.5 Verify Optimization (2026-07-01)"** (vQpBTsCE7R), owner **Yeqi Huang**,
  under Hybrid Serve › Topic Threads › Hybrid Verifier.
- Deployed on **cu12 / driver-550 H20 node `TencentNode1`** (`ssh TencentNode1`),
  venv `/data1/yeqihuang/kimi-venv`, build scripts `/data2/yeqihuang/`. NOT EIDF.
- It's an **SGLang REMOTE_STANDALONE server** serving HTTP `/generate` (NOT the
  nc_service gRPC), real INT4 weights (`CompressedTensorsWNA16MarlinMoEMethod`).
  `/health` stays 503 (missing openai_harmony) → harness drives `/generate` in
  attach mode.
- Deploy recipe: repo `benchmark/remote_spec_acceptance/{README,CU12_BUILD,
  NSIGHT_ANALYSIS,R7_KERNEL_ROUNDS}.md`. CU12_BUILD.md = build sgl-kernel 0.4.3
  from source for cu12.4/sm90 (disable SM100/FlashMLA, keep FA3, CN mirrors for
  FetchContent). torch 2.11.0+cu126; flashinfer 0.6.12 + xgrammar `--no-deps`.
- **Mock-draft path already exists there:** `run_acceptance.py` launches
  **mock draft + Kimi server** (32-draft cfg,
  SGLANG_LOG_SPEC_VERIFY_FORWARD_TIME=1), single-user decode, checks
  verify_forward p50/p90 vs budget. Attach-mode reuses a running server.
- Perf (bs=1, draft=32): verify_forward 72.3→**20.85ms**; 15ms proven below HBM
  floor (MoE ~11ms immovable). Decode step ~40ms = verify 20.85 + ~18 GPU-idle.

## Env gap for sicheng
- EIDF box `eidf230-dev1` has **NO GPU** (no nvidia-smi) → can't host a real model.
- Running the real model needs a GPU node: either TencentNode1 (Yeqi's Kimi
  server) or an EIDF GPU partition (unverified this account has one). The gRPC
  verifier at 10.22.28.100:32245 is the EIDF-reachable real endpoint.
