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
- [ ] Run the full mode-B PD/spec-dec sim loop on CS-3 with `mock_verify_host failures:0`.
- [ ] Run partial-accept on device and connect the real GPU verifier.
- [ ] Complete mode-A transport hardening for `PD_REAL_DAEMON_DEV`.

## Decisions

| Date | Decision | Rationale | Link |
| --- | --- | --- | --- |
| 2026-06-29 | Use in-process gRPC patch plus batch d2h receive as the SpecDec backbone. | It was the fastest measured path; batch receive made d2h host-receive-bound and transferred to the real decode kernel. | `memory/topics/specdec-d2h-latency.md` |
| 2026-07-04 | Preserve mode A and mode B as separate product paths. | Mode A re-ingests per-request KV for regular PD serving; mode B keeps one request's KV and rewinds decode position after verifier acceptance. | `memory/topics/specdec-cs3-roadmap.md` |
| 2026-07-04 | Token-granular decode rewind is required for real SpecDec. | Real `draft_len` around 16 can accept non-P-aligned positions; v2 validates arbitrary accepted position A on sim and real WSE-3. | `memory/topics/specdec-cs3-roadmap.md` |

## Next actions

- [ ] Run `waferengine/samples/specdec/realkv/run_e2e_pd_modeb_sim.sh 2` on the CS-3 login node in the `csl` conda env with `export PYTHONPATH=.` and `IOP_REAL_KERNELS_SRC_{PREFILL,DECODE}` set; success criterion is `mock_verify_host` `failures:0`.
- [ ] After full sim loop passes, run partial-accept on device and connect the real GPU verifier service.
- [ ] Re-run real-kernel PD device transport path (`PD_REAL_DAEMON_DEV`) with `READY_TIMEOUT=7200`, the send_x N-header fix, and ingress-502 retry hardening.
- [ ] Periodically rebase `lexu/decode-rewind` against PR #13 head and consider upstreaming rewind.
- [ ] Verify live repo/server state before acting; memory records branch/test history, not current proof.

## Narrative progress log

### 2026-07-06

- Migrated current status/focus/next-action prose into this plan. No dated inbox items were present; detailed validation history remains in `memory/topics/specdec-cs3-roadmap.md` and `memory/topics/specdec-d2h-latency.md`.
- Converted `memory/context.md` and `tracking/status.md` into thin generated projections that point here and to topic notes.

### 2026-07-04

- Roadmap topic captured real-kernel PD adapters, device validation, decode rewind v1/v2, mode-B adapter progress, framework dispatch, exchange-batch sim pass, and the unrun full-loop runner.

### 2026-06-29

- Real-GPU verifier-side latency measured and ContextBase log `GOZQ9I8pOe` updated; d2h latency topic created.
