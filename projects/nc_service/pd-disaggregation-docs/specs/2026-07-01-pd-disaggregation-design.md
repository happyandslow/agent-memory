# PD Disaggregation for the spec-dec sample — design

**Date:** 2026-07-01 · **Owner:** Le Xu · **Repo:** `nc_service` · **Sample:**
`waferengine/samples/specdec` · **Status:** design (pre-implementation)

## Goal

Restructure the single-runtime, decode-only spec-dec sample into a **prefill/decode
(PD) disaggregated** scheme: two independent runtimes — one running a **prefill**
CSL kernel, one running a **decode** CSL kernel — driven by one gateway driver, with
the **KV cache transferred directly between the two runtimes** over a
worker-to-worker network path.

This is **disaggregation**, explicitly *not* on-wafer co-residence. A prior session
(`WaferEngine`, branch `lexu/mock-nc-executor-daemon`) proved two kernels
**co-resident in one `SdkLayout`** on one wafer (`TWO_PASSTHROUGH_CORESIDENT_PASS`;
real qwen3 co-residence PARTIAL — exchange-1 hang). That is a different architecture.
Here the two kernels live on **two separate wafers / worker processes** and exchange
KV over the host network, so the KV path is the new first-class artifact.

### Scope decisions (locked with user, 2026-07-01)

1. **Passthrough kernels first.** Both runtimes run *passthrough* kernels
   (prefill-passthrough + the existing decode passthrough). Real qwen3
   prefill/decode kernels are under development and not yet available; they swap
   in later (ingress-only change — see §7). Compute is mocked; the **plumbing +
   KV transport** is what this milestone proves.
2. **Direct pod-to-pod KV transport now** (not gateway-mediated). Worker↔worker
   over the EPCC underlay `net1`: **TCP first, RDMA-Write as the upgrade**.
3. **Protocol (`.proto`) unchanged.** Prefill and decode are encoded in the
   *existing* protobuf messages (see §3). No new gRPC message, no wire stage flag.
4. **Two real wafers** for bring-up, both running passthrough kernels.
5. **Driver introduces the two workers; the workers then build the direct
   connection themselves** (rendezvous via the driver, data path pod-to-pod).
6. **KV size is computed from the real prefill-stage config**; passthrough
   transfers that many **mocked** bytes.

## Prior art this builds on (references)

- **Protocol encoding of prefill vs decode:** ContextBase *"SpecDec verify↔draft
  protocol: prefill vs decode — does the wire need to change? (No)"* (`SEOAxhYoeW`).
- **Worker↔worker direct connection + RDMA:** `WaferEngine` branch
  `lexu/h2d-explore`, `h2d-playground/rdma-explore/` — `dispatch_pingpong.py`
  (controller launches **two** pods, hands each the peer's IP/GID via the
  `download_artifact` rendezvous pattern from `e5-direct-link-hack/dispatch_probe.py`,
  pods connect **directly**; **TCP control channel for rendezvous**, **RDMA-Write
  data path**), `tcp_pump.py` (TCP `sendall` fallback), `rdmaw_ctypes.py` /
  `rdmaw_bench.py` (RDMA-Write via `libibverbs` ctypes — no pyverbs, no root
  needed; `/dev/infiniband/*` are 0666).
- **Multi-stage pipeline primitives (the RDMA upgrade target, "task #15"):**
  `h2d-playground/{e6,e7,e8,e10,e11,e13,e14}/` — `pipeline_stage.py`,
  `dispatch_pipeline.py`, `wire.py` (`send_array` / `recv_array`), `topology.py`.
  Only `wire.send_array/recv_array` swaps from TCP `sendall` to
  `ibv_post_send(WRITE)/poll_cq`; the rendezvous stays TCP.
- **Bandwidth ground truth:** e16 — worker↔worker underlay TCP ~9 GB/s (verified);
  e17 — RoCE RDMA-Write ~12.3 GB/s steady-state (= one 100 GbE link; the chip's
  150 GB/s = 12 links needs ~12 hosts, unreachable from one pod).
- **KV on-disk layout:** `h2d-playground/orca_kv_pack_mini/src/kv_format.py`,
  `load_kv_cache.py`.
- **Existing qwen3 chain (layout/reshard reuse, when real kernels land):**
  `WaferEngine/models/qwen3_1p7b-decode/integration/` — `prefill_kv_unshard.py`
  (`unshard_wire`), `device_reshard.py` (`kv_to_device`/`kv_from_device`).

## 1. Topology

```
                         ┌───────────────── gateway driver (one process) ──────────────────┐
                         │  gateway_frontend.run_session (DraftControl client)              │
   GPU / verify ──①────► │   routing: first advance (base_len==0) → prefill; else → decode  │
   (mock_verify_host)    │   pump_prefill ──②──┐            pump_decode ──②──┐               │
                         └─────────────────────┼────────────────────────────┼───────────────┘
                                               │ (inproc patch bridge)      │ (inproc patch bridge)
                                    ┌──────────▼──────────┐      ┌──────────▼──────────┐
                                    │  PREFILL runtime    │      │  DECODE runtime     │
                                    │  wafer A (real)     │      │  wafer B (real)     │
                                    │  prefill_pt.csl     │      │  passthrough.csl    │
                                    │  ingest prompt →    │      │  consume KV (H2D) → │
                                    │  emit KV (D2H)      │      │  draft_advance      │
                                    │  kv_channel: SENDER │─────►│  kv_channel: RECVER │
                                    └─────────────────────┘  ④  └─────────────────────┘
                                          runtime↔runtime KV (net1: TCP → RDMA), keyed by request_id
```

Each runtime is one **in-process-patched worker** (the existing hot-swap `:9000`
server — reused ×2). The gateway driver holds two bridges/pumps. **KV bytes flow
pod→pod on leg ④ and never transit the gateway.**

## 2. Request lifecycle (one session)

1. GPU stub sends a **prefill trigger** (§3) carrying the prompt.
2. Gateway sees `base_len == 0` (session start) → routes to **`pump_prefill`**.
   Prefill kernel ingests the prompt, emits the KV blob, drains it D2H; the prefill
   pod's `kv_channel` **pushes the KV to the decode pod** (keyed by `request_id`).
   Prefill returns an ack (+ the first sampled token).
3. Decode pod holds the received KV in a host buffer (RAM) and H2D-loads it into
   the decode kernel — no filesystem hop.
4. Subsequent `DraftAdvanceCommand`s (steady state, `accepted>0`) route to
   **`pump_decode`**; the decode kernel already holds the KV, emits the egress as
   **one batched `MOV32`** (`VERB_EXCH` / `exchange_batch` — single receive of the
   whole egress) → returns `draft_ids[draft_len]`; gateway reconstructs
   `DraftAdvanceResponse` (unchanged).

## 3. Protocol reuse — prefill & decode in the SAME messages (`.proto` unchanged)

Per ContextBase `SEOAxhYoeW`. `DraftAdvanceRequest` models two composable verbs
(`commit` + optional `next_proposal`), not stages. In `translate.request_to_payload`:
`num_accepted = min(accepted_draft_tokens, len(emitted_ids))`;
`correction_ids = emitted_ids[num_accepted:]` → the wafer ingests corrections.

- **Prefill = a commit-only** `DraftAdvanceRequest{ accepted_draft_tokens=0,
  emitted_ids=prompt, base_len=0 }` → all prompt tokens become corrections →
  the drafter ingests the whole prompt = prefill. (Not "prompt was accepted";
  `accepted=0` routes it through the ingest path.)
- **Decode** = commit with `accepted>0` (+ `next_proposal{k}`), as today.
- **Routing is executor/gateway-side**, keyed on `base_len==0` / first-advance →
  prefill runtime; else decode runtime. Nothing on the wire tags the mode.
- **One internal leg-2 flag:** `codec.py` sets a `FLAG_PREFILL` bit in the existing
  `flags` word so the executor frame is self-routing (an internal io_pipeline
  change, **not** a gRPC change). `frame.py` is already variable-length.
- Prefill ingress is self-describing: `[num_tokens, tok_0 … tok_{n-1}]` — the one
  header the real prefill kernel will also need (decode's analog of `num_correction`).

`.proto` files and gRPC envelope: **zero change.**

## 4. Runtime↔runtime KV channel — `kv_channel.py` (new)

**Invariant: KV never touches disk.** The path is entirely in host RAM —
prefill **D2H drain → in-memory buffer → `kv_channel` (TCP/RDMA) → in-memory
buffer → H2D into decode**. No `.npz`, no `cfg["kv_cache_file"]`, no filesystem
staging. (This is the deliberate departure from the old qwen3 chain, which wrote
`_runs/kv_chip/req*.npz` to the in-pod filesystem and read it back — that hop is
exactly what disaggregation removes.)

A pod-side module running **inside each patched worker**, modelled on
`rdma-explore` + the `pipeline_stage`/`wire` primitives:

- **Rendezvous (driver-introduced, TCP control):** the gateway driver launches both
  workers, then hands each the peer's underlay IP/port (+ RDMA GID/QPN when RDMA is
  on) and a `request_id` correlation, using the `download_artifact` pattern from
  `rdma-explore/dispatch_pingpong.py`. After introduction the two workers hold the
  connection themselves.
- **Data path:** decode pod runs a **receiver** (binds underlay `net1`); prefill pod
  runs a **sender** (drains KV D2H, connects, sends `kv_bytes`, keyed by
  `request_id`). Backend ladder behind one interface (`send_array`/`recv_array`):
  1. **TCP `sendall`** (`tcp_pump.py` shape) — bring-up + correctness.
  2. **RDMA-Write** (`rdmaw_ctypes.py` shape — `libibverbs` via ctypes) — the
     bandwidth upgrade; control channel stays TCP, only the per-transfer op swaps.
- **Interface is transport-agnostic** so simfab/dev can run loopback TCP and the
  cluster can run net1 TCP → RDMA without touching callers.

## 5. KV oracle & sizing (mocked contents, realistic size)

- **Size** from the real prefill config: `kv_bytes = n_layers · 2(K,V) · n_kv_heads
  · head_dim · dtype_bytes · seq_len · bsz`. Qwen3-1.7B (28 layers, 8 KV heads,
  head_dim 128, bf16) → **112 KiB/token**: `PREFILL_LEN=256` → **~28 MiB**;
  `MAX_SEQ_LEN=512` → ~56 MiB; the sim config (7 layers/2 heads/16 dim, L=16) →
  ~14 KiB for dev/simfab. Config carries the dims; `codec.derive_counts` (or a new
  `kv_sizing`) computes `kv_bytes`.
- **Contents mocked** (passthrough): the prefill kernel emits a
  deterministic-from-prompt buffer (e.g. a per-position checksum) of `kv_bytes`.
  The decode passthrough folds the received KV into its draft-id derivation so a
  **dropped / corrupted / misrouted KV is caught numerically** by the existing
  mock-verify accounting — the same oracle discipline as today's
  `(num_accepted+1)*1000+i` draft ids.

## 6. Components (in `nc_service/waferengine/samples/specdec`)

| Component | Change |
|---|---|
| `mock_verify_host.py` | Emit an initial **prefill trigger** (commit-only, prompt in `emitted_ids`, `base_len=0`) then the steady-state decode loop; keep accounting validation. |
| `gateway_frontend.py` / `driver_main.py` | **Dual-pump**: route first advance → `pump_prefill`, rest → `pump_decode`; drive the two-worker **rendezvous** (introduce peers). |
| `translate.py` / `codec.py` | Encode `FLAG_PREFILL`; carry `num_tokens` + prompt in the frame; compute `kv_bytes`; prefill ack/first-token in the response projection. |
| `kernel/prefill_pt.csl` | **New** passthrough prefill: ingest `[num_tokens, ids…]`, emit `kv_bytes` mock KV (+ first token) once. |
| `kernel/passthrough.csl` | Extend decode passthrough to **consume a KV blob** at session init (H2D) and fold it into the draft-id oracle. Egress stays the **single batched `MOV32` / `MEMCPY_32BIT`** emit (`emit_mode="batch"`) → one host `receive` of the whole `draft_len·south_wlts` egress (`exchange_batch`), i.e. the validated batch path (~0.166 ms ring), **not** per-step stream. |
| `appliance.py` / `appliance_handlers.py` | `PrefillAppliance` (drains KV, invokes `kv_channel` sender) + `DecodeAppliance` (receives via `kv_channel`, H2D-loads KV). |
| `kv_channel.py` | **New** pod-side worker↔worker transport (TCP → RDMA) + driver-side rendezvous helper. |
| `config/` | KV dims (`n_layers`, `n_kv_heads`, `head_dim`, dtype), prompt/seq sizing; per-runtime kernel select. |

## 7. Real-kernel swap (later; out of scope for this milestone)

When the real qwen3 kernels land: **ingress-only** change (decode ingests f16
embeddings, prefill ingests i32 token ids; egress south-blob already shared). The
KV layout reshard reuses `prefill_kv_unshard.unshard_wire` (drain wire → canonical)
and `device_reshard.kv_to_device` (canonical → per-PE) from the qwen3 integration
tree — but applied **in-memory on the drained/received buffers**, not via the
chain's intermediate `.npz` files. These are pure numpy, transport-independent
transforms, so the disk-free `kv_channel` is unaffected: prefill reshards the
drained buffer before `send`, or decode reshards the received buffer before H2D
(placement TBD at swap time).

## 8. Milestones

- **M1 — control plane (stub, no SDK, dev-box testable):** GPU stub emits prefill
  trigger; gateway routes first-advance → prefill **stub** handler (returns first
  token), rest → decode stub. Proves dual-path routing + protocol reuse + rendezvous
  handshake. No wafer, no KV bytes yet.
- **M2 — two passthrough appliances + direct KV, TCP:** `prefill_pt` + decode
  passthrough on **two real wafers**; KV drained → sent (net1 TCP) → H2D-loaded;
  oracle green; realistic `kv_bytes`. Latency breakdown per leg.
- **M3 — RDMA-Write data path:** swap `kv_channel` data op to RDMA-Write
  (`rdmaw_ctypes`); rendezvous stays TCP; compare ④ TCP vs RDMA at 28 MiB.
- **M4 (later) — real qwen3 kernels** (§7).

## 9. Risks / open items

- **Two concurrent wafer allocations** on EPCC CS-3 — bring-up needs two appliance
  jobs at once; confirm schedulability (fallback: one real + one simfab, or
  sequential bring-up of the transport with one wafer looped back).
- **RDMA headers stripped in-pod** (per `rdma-explore`): `perftest`/UCX and
  libibverbs headers are absent; `libibverbs.so` is loadable via ctypes. RDMA path
  uses `rdmaw_ctypes.py` (ctypes → verbs), or cross-compiled/vendored headers.
- **Two `mlx5` HCAs, one usable** per pod (`mlx5_0` has GID/IP; `mlx5_1` link-up but
  no IP) → one 100 GbE link/pair; aggregation is out of scope.
- **KV H2D load into a resident (patched) decode kernel** mid-session — the decode
  appliance must accept the received in-memory KV buffer and H2D-load it before the
  first draft-advance; sequence it in `DecodeAppliance` init vs the exchange loop.
  (The qwen3 chain did this file-based at launch; here it is a direct in-RAM upload
  of the buffer handed over by `kv_channel`.)
- **CS-3 SSH `cs3-manual-cm`** protocol (parked ControlMaster; `CS-3-cmd` only;
  never cold-OTP burst — fail2ban risk). Use the `cs3-runner` skill.

## 10. Success criteria

- GPU stub triggers prefill via the **unchanged** protocol; gateway routes
  prefill→decode across **two runtimes** under **one driver**.
- KV of **realistic size** (28 MiB) moves **pod-to-pod directly** (not via gateway,
  **never via disk** — D2H buffer → network → H2D buffer, all in host RAM), keyed by
  `request_id`; oracle catches any KV delivery fault.
- Per-leg latency breakdown incl. leg ④ (KV transfer) for **TCP and RDMA**.
