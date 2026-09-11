# Connecting the Cerebras drafter to hybrid-nn on gala2 — 2026-09-11

**Project:** nc_service
**Author:** codex
**Status:** captured

## What happened / finding

- When setting up the newly requested Chivier/hybrid-nn verifier, do not reuse the older
  SGLang interop assumptions. Authenticated clone `/home/lexu/hybrid-nn` is based on
  `b72b7bb3e6e36adec6d507f271cf3e760fdc54d4`. It contains a historical co-resident
  llama.cpp path, a Transformers round08 1.6B verifier gate, and a full Kimi K2.6
  `engine/` path. Only the last is the target started here.
- Upstream supplies verifier loops plus a drafter HTTP client, not an independent
  verifier listener. Added local `engine/server.py` and `scripts/serve_local_verifier.sh`:
  `127.0.0.1:18090`, `/health` and `/generate`, one request at a time, full 61-layer
  Kimi target on shared physical GPU 4, streaming weights, fp32 attention/KV, 18%
  PyTorch allocator cap, context allocation 128 and maximum K=16. No other GPU process
  was stopped. This is correctness readiness, not throughput evidence or a GPU reservation.
- Existing weights and environment are read-only dependencies: Python at
  `/data/yeqi/hybrid-nn/venv-cute/bin/python` (torch 2.12.0+cu130, Cutlass DSL 4.7.1),
  GGUF reader under `/data/yeqi/kimi-eagle/src/llama.cpp/gguf-py`, and eight Kimi GGUF
  shards under `/data/yeqi/kimi-eagle/models/unsloth/Kimi-K2.6-GGUF/UD-Q2_K_XL`.
  Use `python -P` plus explicit PYTHONPATH. Launcher paths are overridable. No package
  installation into another user's environment occurred.
- Real GPU/HTTP gate passed on one prompt: K=4 acceptance `[0,0,0]`, `[2,2,2]`, `[4,4]`;
  K=16 acceptance `[16]`; actual CuteDSL backend; malformed draft rejection and recovery;
  responsive health and HTTP409 during inference. Outputs matched an independent
  18-token baseline prefix. Drafter was a CPU oracle/adversarial fixture, not Cerebras.
- Found and fixed first-prefill EOS omission in `engine/engines.py`: six regression
  subcases (3 variants x 2 EOS IDs) failed before and pass after. Restarted service and
  confirmed real baseline and CuteDSL speculative generation after the fix. Full HTTP
  gate predates this two-line logic fix; post-fix targeted evidence is separate.
- HTTP DraftFn sends `{prefix_ids,id_last,k}` and expects `{draft_ids}`. Prefix excludes
  id_last. Target verifies K+1 positions, accepts m, commits m+1, crops KV. There are
  no request identity/reset/rollback/finish RPCs in this HTTP schema; a resident draft
  needs a stateful adapter. The temporary test peer on 18091 stops when the gate ends;
  a live verifier listener alone does not mean a drafter is connected.

## Implications / next actions

- **Compatibility blocker:** current Cerebras Qwen3 tokenizer has 151669 IDs and padded
  embedding vocab 151936; Kimi uses vocab 163840 with different token meanings/EOS.
  Numeric IDs cannot be passed unchanged. Keeping Kimi target requires a compatible
  draft checkpoint/tokenizer. Round08 is a candidate but has 20 layers, head_dim256,
  heads8/KV4, FFN5632 versus existing SD's 28 layers, head_dim128, heads16/KV8, FFN6144.
  Adopting it requires kernel/weights/config/numerical validation, not reuse of the
  current compiled SD artifact. No such port has been performed.
- **Proposed, not user-approved implementation:** add verifier-side GrpcDrafter and
  DraftControl listener; preserve CS3 gateway's outbound OpenStream connection and
  existing nc_service ledgers. Initial commit is prompt+first target token; subsequent
  commits carry accepted proposal prefix+correction/bonus. Include final commit/cleanup,
  replay handling, fixed K=16, and cold-load timeout distinct from warm-round timeout.
  Alternative early gate: generalize hybrid's Transformers path to a Qwen-tokenizer
  target; that would be a different model pairing, not Kimi integration.
- No nc_service runtime or kernel changed in this step; hybrid changes remain uncommitted.
  Service PID is in the run directory, not a durable fixed identifier. Inspect health,
  ownership, and GPU availability before reuse/restart.

## Pointers

- `/home/lexu/hybrid-nn/docs/local-verifier.md`: architecture, API, launch, dependencies,
  measured gate scope and proposed integration.
- `/home/lexu/nc_service/_runs/hybrid_verifier_20260911/`: `http_gate.json`,
  `post_eos_gpu.json`, `provenance.json`, `eos_before.log`, `eos_after.log`, `server.pid`,
  active `server_after_eos.log` and original `server.log`.
- `/home/lexu/nc_service/proto/{control,draft}.proto` and
  `waferengine/samples/specdec/sd_service.py`: actual existing stateful contract.
