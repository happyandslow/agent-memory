# nc_service Plan

Human-maintained roadmap and durable progress narrative. This is the canonical home for project goals, milestones, decisions, and next actions. Generated/current status belongs in `tracking/status.md`.

## Goals

- Deliver WaferEngine SpecDec on WSE-3 with CS-3 as the draft model and an external GPU host as verifier/target.
- Keep regular PD serving (mode A) separate from speculative decoding with decode-position rewind (mode B).
- Preserve validated real-kernel/CS-3 findings in topic notes while using this plan for the current roadmap and next actions.

## Milestones

- [x] PD disaggregation framework merged (`driver_main --pd`, pod-to-pod `kv_channel`, appliance factory seam).
- [x] Real qwen3 prefill+decode adapters wired into the PD framework; `PD_REAL_SIM_PASS` recorded.
- [x] Single real appliances validated bit-exact on real WSE-3 (`DECODE_RESIDENT_DEV_PASS`, `PREFILL_RESIDENT_DEV_PASS`).
- [x] Decode rewind v1 and token-granular v2 validated bit-exact in sim and on real WSE-3.
- [x] Mode-B adapter increments recorded: sim pass, device window pass, partial-accept accounting fix, full adapter-chain `MODEB_DEV_PASS`, framework factory dispatch, exchange-batch sim pass.
- [x] Mode-B PD module/process architecture trace delivered to PR #10 and contextbase (`memory/topics/specdec-modeb-pd-module-trace.md`).
- [ ] Run the full mode-B PD/spec-dec sim loop on CS-3 with `mock_verify_host failures:0`.
- [x] Validate hosted GPU verifier transport with EIDF Kubernetes SGLang REMOTE_STANDALONE and Rust mock draft.
- [x] Boot and measure real Kimi K2.5 verifier on EIDF 8×H100 with known-good flags (17 ms p50 32-token verify_forward).
- [ ] Run partial-accept on device and connect the real GPU verifier to the real CS-3 draft path.
- [ ] Complete mode-A transport hardening for `PD_REAL_DAEMON_DEV`.
- [ ] Split the new prefill `egress` bottleneck (prefill compute + D2H lumped) with on-wafer TSC-at-emit vs host receive timing.

## Decisions

| Date | Decision | Rationale | Link |
| --- | --- | --- | --- |
| 2026-06-29 | Use in-process gRPC patch plus batch d2h receive as the SpecDec backbone. | It was the fastest measured path; batch receive made d2h host-receive-bound and transferred to the real decode kernel. | `memory/topics/specdec-d2h-latency.md` |
| 2026-07-04 | Preserve mode A and mode B as separate product paths. | Mode A re-ingests per-request KV for regular PD serving; mode B keeps one request's KV and rewinds decode position after verifier acceptance. | `memory/topics/specdec-cs3-roadmap.md` |
| 2026-07-04 | Token-granular decode rewind is required for real SpecDec. | Real `draft_len` around 16 can accept non-P-aligned positions; v2 validates arbitrary accepted position A on sim and real WSE-3. | `memory/topics/specdec-cs3-roadmap.md` |

## Next actions

- [ ] Run `waferengine/samples/specdec/realkv/run_e2e_pd_modeb_sim.sh 2` on the CS-3 login node in the `csl` conda env with `export PYTHONPATH=.` and `IOP_REAL_KERNELS_SRC_{PREFILL,DECODE}` set; success criterion is `mock_verify_host` `failures:0`.
- [ ] After full sim loop passes, run partial-accept on device and connect the EIDF/SGLang hosted verifier to the real CS-3 draft path.
- [ ] Re-run real-kernel PD device transport path (`PD_REAL_DAEMON_DEV`) with `READY_TIMEOUT=7200`, the send_x N-header fix, and ingress-502 retry hardening.
- [ ] If one-time KV handoff remains important after egress is split, replace the npz handoff container with a raw header plus contiguous arrays to reclaim encode/handoff/tobytes overhead.
- [ ] Periodically rebase `lexu/decode-rewind` against PR #13 head and consider upstreaming rewind.
- [ ] Verify live repo/server state before acting; memory records branch/test history, not current proof.

## Narrative progress log

### 2026-07-15

- Drained six EIDF GPU-verifier inbox notes into `memory/topics/specdec-gpu-verifier-eidf.md`. Durable state: the SGLang `REMOTE_STANDALONE` hosted verifier runs in EIDF Kubernetes namespace `eidf230ns`; the Rust mock draft validates the DraftControl loop against dummy SGLang; real Kimi K2.5 **does fit and serve** on the 8×H100 pod with weight-loader prefetch/skip-warmup flags, yielding ~17 ms p50 GPU-side 32-token verify_forward. Earlier “does not fit” note is superseded as a load-phase/CephFS failure, not true OOM.

### 2026-07-09

- Drained `memory/inbox/2026-07-09-kv-handoff-zerocopy-and-rdma-negative.md` into `memory/topics/specdec-modeb-drive-path.md` and this plan. Durable finding: the KV handoff zero-copy seam (`23ab43a`) is device-confirmed, cutting decode unframe 789.9 → 23.0 ms and full 43-round run 4494.3 → 3136.7 ms.
- Preserved RDMA as a negative result: after fixing controller env authority (`e8f8feb`) and RDMA auto-GID/device selection (`dc60b4e`), pod-to-pod RDMA engaged but did not improve r0 handoff (~2283 ms RDMA vs ~2196 ms TCP), proving the wire was not the bottleneck.
- Updated next actions around the remaining bottleneck: prefill `egress` is still a host bracket around prefill compute plus 128 MB KV readback, and needs TSC/host timing before optimization.

### 2026-07-07

- Drained module-by-module trace of `run_e2e_pd_modeb_real.sh`: four processes (verifier, gateway, decode pod, prefill pod), three couplings (DraftControl, two in-process-patch bridges, KV side-channel), and the appliance factory seam that swaps only decode for mode B.
- Delivered the annotated architecture diagram to PR #10 under `docs/pd-disagg/` and posted the PNG/PDF to contextbase (`2026-07-07-mode-b-pd-workflow-module-trace-figure-pdf-5tgGAhxEZx`). Operational gotchas: do not manually consume the Outline MCP OAuth refresh token; current render path is `wkhtmltopdf`/`ghostscript`/`pdftoppm`, not Chromium.

### 2026-07-06

- Migrated current status/focus/next-action prose into this plan. No dated inbox items were present; detailed validation history remains in `memory/topics/specdec-cs3-roadmap.md` and `memory/topics/specdec-d2h-latency.md`.
- Converted `memory/context.md` and `tracking/status.md` into thin generated projections that point here and to topic notes.

### 2026-07-04

- Roadmap topic captured real-kernel PD adapters, device validation, decode rewind v1/v2, mode-B adapter progress, framework dispatch, exchange-batch sim pass, and the unrun full-loop runner.

### 2026-06-29

- Real-GPU verifier-side latency measured and ContextBase log `GOZQ9I8pOe` updated; d2h latency topic created.
