---
summary: EIDF/Kubernetes SGLang REMOTE_STANDALONE verifier bring-up, dummy and real Kimi K2.5 measurements.
tags: [nc-service, specdec, gpu-verifier, eidf, sglang, kimi, glm, mtp]
---

# SpecDec GPU verifier on EIDF / SGLang REMOTE_STANDALONE

## Summary

The GPU verifier surface for nc_service is the SGLang `REMOTE_STANDALONE` hosted verifier: SGLang serves the target/verifier model over HTTP and hosts a DraftControl gRPC server that the WSE/CS-3 draft service dials. Registering the draft alone does not emit commands; an in-flight HTTP `/generate` request drives `DraftAdvanceCommand`s.

## Access and deployment surface

- The `sicheng` path reaches `eidf230-dev1.vms.os.eidf.epcc.ed.ac.uk` via `ssh -J sicheng@eidf-gateway.epcc.ed.ac.uk sicheng@10.24.7.82`; reuse a ControlMaster and back off after rapid SSH failures because the gateway rate-limits.
- `eidf230-dev1` is a no-GPU dev VM. The real service runs in EIDF Kubernetes namespace `eidf230ns`; `kubectl` uses `/kubernetes/config` and commands must pass `-n eidf230ns` because the default namespace has no rights.
- Live pod observed: `kimi-k25-sglang-h100-bdwk4` on 8×H100-80GB. HTTP listens on `:30000`, gRPC verifier on `:50050`; NodePorts include gRPC `32245` (the old `10.22.28.100:32245` endpoint targets this pod's `50050`).
- The hosted verifier fork is not stock `/sgl-workspace/sglang`; it lives at `/tmp/sglang-unit/python` inside the pod. Set `PYTHONPATH=/tmp/sglang-unit/python`, but note `/tmp` is ephemeral if the pod restarts.

## Validated dummy/mock-draft loop

- Rust `verify_service` / `draft_service` build and test on the EIDF dev VM without CUDA; the Rust layer is transport/benchmark logic and GPU-agnostic.
- With SGLang dummy `Qwen/Qwen3-0.6B --load-format dummy`, `kubectl port-forward` of `50050` and `30000`, Rust `draft_service` with `DRAFT_SERVICE_VARIANT=direct`, and a `/generate` request produced 16 `DraftAdvanceCommand`s and HTTP 200. Zero accept rate is expected with garbage mock draft ids vs dummy logits.
- `DRAFT_SERVICE_ID` must match the SGLang `--remote-draft-service-id` (default `draft-service-1`). Use `stdbuf -oL -eL` for redirected Rust logs or wait for clean process exit; otherwise block-buffered stdout can hide benchmark-complete lines.

## Real Kimi K2.5 on 8×H100 — corrected outcome

A first attempt made it look like real Kimi K2.5 did not fit on H100-80GB, but the later known-good run corrected that: the failure was a slow/flaky CephFS load-phase/rank failure, not true OOM.

Known-good flags:

- Model `/ckpt/moonshotai/Kimi-K2.5`, TP=8, INT4 compressed tensors, `--trust-remote-code --language-only`.
- `--weight-loader-prefetch-checkpoints --weight-loader-prefetch-num-threads 16` is required for reliable CephFS load.
- `--skip-server-warmup`, hosted `--remote-verify-port 50050`, no legacy `--remote-draft-url`.
- Tight memory configuration: context/max tokens 12288, mem fraction static 0.953, max running requests 1, cuda graph bs/max bs 1, radix cache and overlap schedule disabled.

Validated result on 2026-07-15: server booted and served. Bring-up took roughly 72 minutes (CephFS load + marlin repack), with about 1.08 GB/GPU free after CUDA graph capture. Rust mock draft plus `/generate max_new_tokens=64` drove 63 verify steps; GPU-side 32-token `verify_forward` was about 17.0 ms p50 (p90 17.5, p99 22.9), faster than the earlier H20 20.85 ms report. The dummy rig should be restored afterward unless Le/Yeqi intentionally keep real Kimi up.

## Commands / gotchas

- Hosted verifier shape:
  `python3 -m sglang.launch_server --model-path <TARGET_MODEL> --speculative-algorithm REMOTE_STANDALONE --speculative-num-steps K --speculative-num-draft-tokens K+1 --speculative-eagle-topk 1 --remote-verify-host 0.0.0.0 --remote-verify-port 50050 --remote-draft-service-id draft-service-1 ...`
- Draft side: `VERIFY_ADDR=http://<verifier-host>:50050 DRAFT_SERVICE_ID=draft-service-1 target/release/draft_service`; for WaferEngine real CS-3 draft, `driver_main.py --bridge launcher --appliance real --draft-len K`.
- Never run `pkill -f "launch_server"` inside an exec command whose own argv includes that string; kill explicit PIDs or use a pattern not present in the exec wrapper.
- Coordinate with Yeqi before relaunching real Kimi or consuming the shared 8×H100 pod. Each real-weight bring-up is expensive.

## Drained inbox notes

- `memory/inbox/2026-07-14-gpu-verify-service-eidf-bringup.md`
- `memory/inbox/2026-07-14-real-verify-model-deployment-pointers.md`
- `memory/inbox/2026-07-14-sglang-remote-verifier-run-recipe.md`
- `memory/inbox/2026-07-15-gpu-verify-service-eidf-k8s-VALIDATED.md`
- `memory/inbox/2026-07-15-kimi-k25-h100-KNOWN-GOOD-startup-recipe.md`
- `memory/inbox/2026-07-15-real-kimi-oom-80gb-h100-and-fork-location.md` (superseded by the known-good correction above)

## GLM-4.6 FP8 + native MTP baseline on EIDF (2026-07-16)

GLM-4.6-FP8 (`zai-org/GLM-4.6-FP8`, 355B FP8) was validated as an alternative verifier and native MTP competitor baseline on the EIDF 8×H100 pod. Download was fast (~8.5 min at ~675 MB/s) and load was ~4 min, using about 41.9 GB/GPU with ~28 GB free — much easier than Kimi K2.5. Bring-up required disabling custom all-reduce / FlashInfer allreduce fusion because CUDA symmetric-memory multicast/NVLink SHARP was unavailable in the pod; NCCL fallback works but likely penalizes GLM's 92-layer allreduce.

Measured bs=1, cuda-graph, 256-token decode, temp=0 results:

| config | throughput | TPOT | speedup | acceptance |
|---|---:|---:|---:|---:|
| GLM-4.6 vanilla | 58 tok/s | 17.2 ms | 1× | — |
| GLM-4.6 + MTP | 85.5 tok/s | 11.7 ms | 1.47× | accept_len 1.80; accept_rate 0.80 |

Interpretation: this gives a same-hardware measured GPU-spec-dec competitor band of ~1.47× unoptimized, with published/optimized MTP closer to ~1.8×. The CS-3 draft path should compare against 1.47–1.8× if GLM is used as verifier; GLM vocab is 151552 versus Kimi's 163840, so a GLM verifier path would need draft retraining or a compatible draft.
