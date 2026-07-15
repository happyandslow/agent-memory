# Real Kimi K2.5 does NOT fit for serving on 8×80GB H100 (OOM) + fork-sglang location gotcha

Date: 2026-07-15. Tried to restart the eidf230ns verifier pod
(`kimi-k25-sglang-h100-bdwk4`) from dummy → real Kimi K2.5 for a 32-token verify
latency measurement. Failed; dummy rig restored.

## GOTCHA 1 — the remote-verify sglang is at /tmp/sglang-unit (NOT /sgl-workspace)
- `/sgl-workspace/sglang` (git main 05ee93c) and pip `sglang` are STOCK — no
  `--remote-verify-port`. The **fork with REMOTE_STANDALONE + remote-verify** lives at
  **`/tmp/sglang-unit/python`** (server_args.py has `remote_verify_port`).
- To launch the hosted verifier you MUST set `PYTHONPATH=/tmp/sglang-unit/python`.
  Plain `python3 -m sglang.launch_server --remote-verify-port ...` → "unrecognized
  arguments" (picks stock). **/tmp is ephemeral** — if the pod restarts, this fork
  checkout is gone; the running server is the only durable copy of that state.
- Restore-dummy command (validated, brings :30000/:50050 back in ~30s):
  `PYTHONPATH=/tmp/sglang-unit/python python3 -m sglang.launch_server
  --model-path Qwen/Qwen3-0.6B --load-format dummy --trust-remote-code
  --skip-server-warmup --speculative-algorithm REMOTE_STANDALONE
  --speculative-num-draft-tokens 17 --speculative-num-steps 16 --speculative-eagle-topk 1
  --remote-verify-host 0.0.0.0 --remote-verify-port 50050
  --remote-draft-service-id draft-service-1 --remote-draft-timeout-ms 30000
  --max-running-requests 1 --disable-radix-cache --disable-overlap-schedule
  --cuda-graph-bs 1 --cuda-graph-max-bs 1 --sampling-backend pytorch
  --context-length 512 --mem-fraction-static 0.5 --host 0.0.0.0 --port 30000`

## GOTCHA 2 — real Kimi K2.5 is too tight to SERVE on 8×80GB H100
- Launched with `--model-path /ckpt/moonshotai/Kimi-K2.5 --tp-size 8
  --speculative-num-steps 31 --speculative-num-draft-tokens 32 ... --mem-fraction-static
  0.9 --context-length 4096`. Arch OK (`KimiK25ForConditionalGeneration`,
  `CompressedTensorsWNA16MarlinMoEMethod`, INT4).
- Weight load from CephFS `/ckpt` = **~26 min** (`Load weight end elapsed=1582s`),
  very bursty per-shard (2–26 s/shard, contention). Post-load: **avail mem = 5.17 GB /
  GPU** (weights = 72.19 GB on 80 GB). Then crashed at KV/graph phase:
  `ValueError: TP rank 6 could finish loading, but other ranks didn't ... (OOM or slow
  node)` → sigquit → process tree killed.
- **Interpretation:** 1T INT4 weights (~72 GB/rank) leave too little on 80 GB H100 for
  KV + CUDA-graph capture + 32-token spec-dec buffers. The report's real Kimi numbers
  (verify_forward 72→20.85 ms) were on **H20 141 GB** TP=8 (`TencentNode1`), not these
  H100s. This is almost certainly WHY the eidf pod only ever ran the dummy Qwen rig and
  merely STAGED Kimi weights. Getting real Kimi to serve here would need
  mem tricks (kv offload / ctx≤1024 / disable-cuda-graph) or is just not viable at 80 GB.
- To measure a REAL 32-token verify number today: either use a model that fits in ≤4 GPU
  (Qwen3-8B/32B, dummy-load gives real-shape latency) or use the H20 (TencentNode1).
- **Do NOT re-attempt real Kimi on these H100s without Yeqi's known-good flags** — each
  attempt costs ~26 min of CephFS weight load.
