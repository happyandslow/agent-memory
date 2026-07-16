# GPU verify service on EIDF k8s — driven by Rust mock draft, VALIDATED

Date: 2026-07-15. The "real GPU service" is deployed on the **EIDF Kubernetes GPU
Status: drained
service**, namespace **`eidf230ns`**, NOT a bare GPU host. Drove it end-to-end with
our Rust mock draft (CS-3 down) — full spec-dec loop proven.

## Access (from the sicheng dev VM eidf230-dev1, which has NO GPU itself)
- `kubectl` at /usr/local/bin/kubectl; `KUBECONFIG=/kubernetes/config` (also
  ~/.kube/config). Context `eidf-general-prod`, user `u-9lvsx`. Context namespace is
  BLANK → defaults to `default` where you have NO rights. **Must pass `-n eidf230ns`.**
- In `eidf230ns`: can-i create pods/jobs/pods-portforward = YES. Quota (compute):
  GPU 8/12 used, CPU 53/100, mem ~0.5/1Ti.
- EIDF gateway rate-limits rapid ssh (`Connection closed by UNKNOWN port 65535`,
  ~10-60min); back off, reuse a ControlMaster.

## The live verifier (already running, 21d)
- Pod **`kimi-k25-sglang-h100-bdwk4`**, node gpu8-vm09, image `lmsysorg/sglang:dev-cu12`,
  8×H100. Pod command is `sleep infinity` (parked); the server was hand-launched via
  exec (pid 35794 python3). SGLang ver `...g4c582c327` = fork `sglang-remote-spec`
  commit 4c582c327 (has REMOTE_STANDALONE).
- **CAUTION: currently serving `--model-path Qwen/Qwen3-0.6B --load-format dummy`
  (integration/smoke rig), NOT real Kimi.** Real Kimi weights are STAGED at
  `/ckpt/moonshotai/Kimi-K2.5` but not loaded. Server args: REMOTE_STANDALONE,
  num-steps 16, num-draft-tokens 17, eagle-topk 1, remote-verify-port 50050,
  remote-draft-service-id **draft-service-1**, timeout 30000ms, ctx 512, memfrac 0.5.
- Listens: HTTP `:30000`, gRPC verify `:50050`. NodePorts: `sglang-reintegrate`
  (30000:32014, 50050:31080) and `nc-verify-nodeport` (50050:**32245**) → both target
  the pod (10.62.111.216). So the old `10.22.28.100:32245` = this pod's gRPC 50050.
- Why my earlier mock-draft probe got 0 commands: verifier only drives the draft
  DURING an in-flight HTTP /generate; idle registration triggers nothing.

## VALIDATED drive recipe (no CS-3, no real weights)
1. `kubectl -n eidf230ns port-forward pod/kimi-k25-sglang-h100-bdwk4 50050:50050 30000:30000`
2. Rust draft: `VERIFY_ADDR=http://127.0.0.1:50050 DRAFT_SERVICE_VARIANT=direct
   DRAFT_SERVICE_ID=draft-service-1 target/release/draft_service` (id MUST match).
3. `curl :30000/generate -d '{"text":"...","sampling_params":{"max_new_tokens":16,"temperature":0}}'`
- Result: HTTP 200, 16 tokens, e2e 0.13s; draft received **16** DraftAdvanceCommands
  (one per token); `spec_accept_rate 0.0`, `spec_num_proposed_drafts 240` — 0% accept
  is EXPECTED (mock proposes garbage ids vs dummy logits). Full loop proven.
- Our Rust `draft_service` IS a contract-compatible draft (OpenStream→Hello→handle
  DraftAdvanceCommand→DraftAdvanceResult); default DRAFT_SERVICE_ID=draft-service-1.

## To run the REAL Kimi model
Exec into the pod and relaunch with `--model-path /ckpt/moonshotai/Kimi-K2.5` + real
load-format (8×H100 TP=8, heavy). Shared resource owned by Yeqi — coordinate first.
The dummy rig is the safe target for pipeline/mock-draft validation.
