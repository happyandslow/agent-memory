# How to run the GPU verify service — SGLang REMOTE_STANDALONE (authoritative)

Date: 2026-07-14. Source: repo `lausannel/sglang-remote-spec` (PRIVATE, happyandslow
Status: drained
has pull+push), PR #1 "Host remote draft verifier" (branch
`remote-draft-grpc-tp-broadcast`), doc committed at ee6c3f6 →
`docs/advanced_features/speculative_decoding.md` § "Remote Standalone Speculative
Decoding".

## What it is
REMOTE_STANDALONE = SGLang runs the TARGET/verifier model AND hosts a `DraftControl`
gRPC server (the nc_service contract) in the SAME process as its HTTP API. The
drafting service is the gRPC CLIENT that dials back and holds a bidi stream. This
is the real bridge between the Kimi/SGLang model and nc_service's draft side.

## Start the verifier (the GPU service) — one process
```bash
python3 -m sglang.launch_server \
  --model <TARGET_MODEL> \
  --host 0.0.0.0 --port 30000 \
  --speculative-algorithm REMOTE_STANDALONE \
  --speculative-num-steps 16 \
  --speculative-eagle-topk 1 \
  --speculative-num-draft-tokens 17 \
  --remote-verify-host 0.0.0.0 \
  --remote-verify-port 50050 \
  --remote-draft-service-id draft-service-1 \
  --remote-draft-timeout-ms 30000
```
- `--port 30000` = HTTP `/generate` `/v1/...`. `--remote-verify-port 50050` = gRPC the
  draft dials. Give the draft a ROUTABLE verifier IP, not 0.0.0.0.
- HARD constraints: `--speculative-eagle-topk 1`; `num-draft-tokens = num-steps + 1`;
  the draft's proposal length `k` (WaferEngine `--draft-len`) MUST equal `num-steps`.
- Legacy opposite-direction transport still exists: `--remote-draft-url
  http://<DRAFT_HOST>:PORT` (SGLang dials a unary DraftRuntimeService). Don't set
  `--remote-verify-port` with it; hosted mode wins if both set.

## Connect a draft
- WaferEngine (needs CS-3 for `--appliance real`):
  `VERIFY_ADDR=http://<HOST>:50050 DRAFT_SERVICE_ID=draft-service-1 python
  waferengine/samples/specdec/driver_main.py --bridge launcher --appliance real
  --ready-timeout 1800 --draft-len 16` (no --max-rounds/--idle-timeout for serving).
- ANY compatible draft works: call `DraftControl.OpenStream`, send `DraftServiceHello`
  with matching `draft_service_id`, handle each `DraftAdvanceCommand`, return
  `DraftAdvanceResult` w/ same `request_id`. => **our Rust `draft_service` (DIRECT
  mock) is already a valid draft** (DRAFT_SERVICE_ID default = draft-service-1). Good
  for CS-3-down smoke tests.

## RESOLVES earlier mystery (mock draft got 0 advance commands @ 10.22.28.100:32245)
The hosted verifier drives the draft ONLY while serving an in-flight HTTP generate
request. Draft registering alone triggers nothing (unlike our Rust verify_service
benchmark which auto-drives on registration). To exercise it: POST to the HTTP API
(`:30000/v1/chat/completions`) THEN the verifier issues DraftAdvanceCommands per
token. (Also 32245 was an older instance; doc standardizes on 50050.)

## "Do I just need sglang access to run it?" — NO, access is necessary not sufficient
Need ALL of: (1) repo access ✓; (2) a GPU node — EIDF `eidf230-dev1` has NO GPU, so
NOT there; (3) built SGLang env (cu12 build per CU12_BUILD.md on H20/driver-550, or
stock SGLang on newer-driver GPU); (4) a `<TARGET_MODEL>` (real Kimi K2.5 INT4, or a
small model / `--load-format dummy` for an integration smoke test — PR#1 verified
integration with dummy weights, completion_tokens:4, pass:true).
