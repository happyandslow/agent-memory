# GPU verify_service bring-up on EIDF (sicheng account) — VALIDATED

Date: 2026-07-14. Goal: prove the GPU-host **verify service** builds+runs on the
EPCC EIDF GPU cluster, driven by a **mock draft** (CS-3 under maintenance).

## Access
- `ssh -J sicheng@eidf-gateway.epcc.ed.ac.uk sicheng@10.24.7.82` works **key-only**
  through the jump (gateway did publickey+keyboard-interactive with NO OTP prompt
  for the `sicheng` identity — unlike the congjiehe/CS-3 route which needs TOTP).
  Parked a ControlMaster (`~/.ssh/cm/gpu-%C`, persist 4h) for reuse.
- Target node = `eidf230-dev1.vms.os.eidf.epcc.ed.ac.uk`, a **dev VM with NO GPU**
  (`nvidia-smi` absent). Code/logs live under `/home/eidf230/eidf230/sicheng/lexu`.

## What "GPU service" is here
The deployable GPU-side service is the **Rust `verify_service`** binary (root
crate `services`), NOT a torch model. It's a pure gRPC/transport+benchmark shell:
listens on VERIFY_LISTEN_ADDR, waits for `draft_service` to dial in and hold one
long-lived bidi `DraftControl.OpenStream`, then (RUN_BENCH=1) pushes sequential
`DraftAdvance` commands. **It does not touch CUDA** — the real GPU verifier model
plugs in later; this repo's Rust layer is GPU-agnostic. (Python
`mock_verify_host.py` is a separate local stand-in used for wafer e2e.)
"Mock drafting" = `draft_service` with `DRAFT_SERVICE_VARIANT=direct` →
`MockDraftRuntime` (no Cerebras needed).

## Bring-up steps (all userspace, no root)
1. Only missing prereq = Rust toolchain. `rustup` minimal → rustc/cargo 1.97.0
   (edition 2024 OK). protoc NOT needed: build.rs uses `protoc-bin-vendored`.
   git/gcc/python3 present; 776G free.
2. rsync only the crate (Cargo.toml/lock, build.rs, src/, proto/).
3. `cargo build --release --bin verify_service --bin draft_service` → clean, 32s.
4. `cargo test --release` → 2 passed (mock runtime).
5. e2e: verify_service(127.0.0.1:50050, BENCH_REQUESTS=200,K=16) + draft_service
   direct. **PASS**: 200/200 advance rounds, qps=4650, latency p50=0.199ms /
   p90=0.278 / p99=0.385 (loopback, same VM).

## Gotcha (cost me a re-run)
Rust `println!` to a redirected file is **block-buffered**; SIGTERM-killing the
process before it flushes DROPS the final "benchmark complete"/latency lines →
looked like a stall at req ~119. Fix: wrap launches in `stdbuf -oL -eL` (or wait
for clean exit). Not a real hang.

## Open / next
- This node has no GPU — fine for transport validation, but a real verifier model
  needs a GPU node on EIDF (check partition/nvidia driver there).
- Only loopback measured; cross-host draft↔verify latency still untested.
