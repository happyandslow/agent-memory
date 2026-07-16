# KNOWN-GOOD: real Kimi-K2.5 verifier boots + serves on EIDF 8×H100-80GB

Date: 2026-07-15. Supersedes the earlier "does not fit on 80GB H100" claim — that was
a LOAD-phase failure (slow/flaky CephFS killing a rank), NOT OOM. With weight-loader
prefetch, all 8 ranks load, KV pool allocates, CUDA graph captures, server comes up
with ~1.08 GB/GPU free. Memory fits. See [[2026-07-15-real-kimi-oom-80gb-h100-and-fork-location]].

## Where / prereqs
- Pod `kimi-k25-sglang-h100-bdwk4` in ns `eidf230ns` (8×H100-80GB), model at
  `/ckpt/moonshotai/Kimi-K2.5` (INT4 compressed-tensors, 555GB, CephFS).
- MUST use the fork sglang: `PYTHONPATH=/tmp/sglang-unit/python` (stock /sgl-workspace
  lacks --remote-verify-port). /tmp is ephemeral — don't restart the POD itself.
- Drive/kubectl from the sicheng VM: `kubectl -n eidf230ns exec kimi-k25-sglang-h100-bdwk4 -- ...`
- WARNING: never `pkill -f "launch_server"` inside an exec whose own cmdline contains
  that string — it kills your own shell (exit 137). Kill by explicit PID or a pattern
  not present in the running script.

## Known-good startup command (hosted transport, stays up idle for a draft to dial in)
```bash
export PYTHONPATH=/tmp/sglang-unit/python
export SGLANG_LOG_SPEC_VERIFY_FORWARD_TIME=1
python3 -m sglang.launch_server \
  --model-path /ckpt/moonshotai/Kimi-K2.5 \
  --trust-remote-code --language-only \
  --host 0.0.0.0 --port 30000 \
  --tp-size 8 \
  --context-length 12288 --mem-fraction-static 0.953 --max-total-tokens 12288 \
  --max-running-requests 1 --chunked-prefill-size 2048 --max-prefill-tokens 4096 \
  --prefill-attention-backend fa3 --decode-attention-backend flashinfer \
  --sampling-backend flashinfer --moe-runner-backend marlin \
  --weight-loader-prefetch-checkpoints --weight-loader-prefetch-num-threads 16 \
  --speculative-algorithm REMOTE_STANDALONE \
  --speculative-num-steps 31 --speculative-eagle-topk 1 --speculative-num-draft-tokens 32 \
  --speculative-attention-mode decode \
  --skip-server-warmup \
  --remote-verify-host 0.0.0.0 --remote-verify-port 50050 \
  --remote-draft-service-id draft-service-1 --remote-draft-timeout-ms 30000 \
  --disable-radix-cache --disable-overlap-schedule \
  --cuda-graph-bs 1 --cuda-graph-max-bs 1
```
Differences vs the crash command: `--skip-server-warmup` (so bring-up doesn't need a
draft), and hosted `--remote-verify-port 50050` instead of legacy
`--remote-draft-url http://127.0.0.1:31000` (draft dials IN → drive with nc_service
Rust draft_service). Keep the prefetch flags — they are what make the load reliable.

## Timing / signposts to watch (bring-up ≈ 40–50 min, CephFS-bound)
- `Rank N: prefetching ... into page cache finished in ~140s` (fast, parallel, 8×16 threads)
- `Multi-thread loading shards: 100% | 64/64` then per-rank `Load weight end. elapsed=~1900–2700s, avail mem=5.1 GB, mem usage=72.19 GB`
- `Capture cuda graph end ... avail mem≈1.08 GB` (all 8 ranks) → `max_total_num_tokens=12288 ... available_gpu_mem≈1.18 GB` → server up, LISTEN :30000 + :50050.
- 32-token verify = num-steps 31 / num-draft-tokens 32 / topk 1. Marlin repack is the slow post-load step (60 MoE layers × 384 experts × 2 ≈ 46k tensors).

## Serve/measure 32-token verify (after it's up)
1. `kubectl -n eidf230ns port-forward pod/kimi-k25-sglang-h100-bdwk4 50050:50050 30000:30000`
2. Rust draft: `VERIFY_ADDR=http://127.0.0.1:50050 DRAFT_SERVICE_VARIANT=direct
   DRAFT_SERVICE_ID=draft-service-1 target/release/draft_service` (built at
   /home/eidf230/eidf230/sicheng/lexu/nc_service).
3. `curl :30000/generate -d '{"text":"...","sampling_params":{"max_new_tokens":64,"temperature":0}}'`
4. Read per-step verify_forward from the server log (SGLANG_LOG_SPEC_VERIFY_FORWARD_TIME=1)
   → the GPU-side 32-token verify latency. Reference: 20.85 ms on H20 (cu12 report).

## RESULT (2026-07-15, MEASURED on device) — reproduced + served
- Reproduced the known-good recipe: boots clean, `The server is fired up and ready to
  roll!` (HTTP :30000 + gRPC :50050). Bring-up ~72 min (18:10→19:22) — CephFS load +
  marlin repack; tail ranks ~20 min each. Server stayed up (no warmup crash).
- Drove it with the Rust mock draft (draft-service-1) + POST /generate max_new_tokens=64:
  HTTP 200, 64 tokens, spec_verify_ct=63, spec_accept_rate=0 (mock=garbage drafts, fine
  for latency), e2e_latency 3.058s → ~48.5 ms/decode-step (incl. mock-draft round-trip).
- **GPU-side 32-token verify_forward (bs=1, cuda_graph=True): gpu_ms p50 ≈ 17.0 ms**
  (p90 17.5, p99 22.9, mean 17.1, min 15.3). host_ms ≈ same. Log line:
  `Spec verify forward timing: bs=1 verify_tokens=32 cuda_graph=True host_ms=17.2 gpu_ms=17.1`.
- Compare: cu12 report 20.85 ms on H20 → **H100-80GB slightly FASTER (~17 ms)** for the
  same INT4 marlin verify at draft=32. So H100 is fine for the verify latency; only the
  ~72-min bring-up (slow storage) is the pain.

## VANILLA decode baseline MEASURED (2026-07-16)
Relaunched Kimi WITHOUT spec-dec (drop all --speculative-* / --remote-*; keep
language-only + prefetch + tuned mem). Bring-up again ~80 min (CephFS+repack).
- **Vanilla decode TPOT = 9.2 ms/token** (steady-state ~108 tok/s, bs=1,
  cuda_graph=True; e2e 2.747s/256tok=10.7ms incl prefill). Server log:
  `Decode batch ... gen throughput (token/s): ~108`.
- Confirms the earlier 8.5ms ESTIMATE (from decomposing verify 17ms). Good.
- **Two GPU-side anchors now both MEASURED: d(vanilla)=9.2ms, v(verify-32)=17ms.**
  Ratio v/d = **1.85** → verify(32) costs only 1.85× a single decode but yields
  up to 32 tokens (fixed cost dominates → spec-dec economically favorable here).
- Break-even (S=A·d/T_round), A≈10 (K16 reported): serial(T_round~29ms)=3.2×,
  pipelined(~17ms)=5.4×. Beat GPU spec-dec(~2×) needs A>3.7 (pipelined)/A>6.3
  (serial); round-latency budget T_round<4.6·A=46ms (met at 17-29ms).
- Still estimated / need CS-3: draft-compute (~9ms K31) and A on K=32/real data.

## Restore afterward (dummy rig, so shared service returns to found-state)
`PYTHONPATH=/tmp/sglang-unit/python python3 -m sglang.launch_server --model-path
Qwen/Qwen3-0.6B --load-format dummy ... --remote-verify-port 50050 ... --skip-server-warmup`
(full cmd in [[2026-07-15-real-kimi-oom-80gb-h100-and-fork-location]]).
