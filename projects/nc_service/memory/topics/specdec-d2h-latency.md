# SpecDec d2h latency + real-GPU verify-side (WSE-3 drafter)

## Summary

Spec-dec on WSE-3: CS-3 is the **draft** model, an external GPU host is the **verifier/target**.
Each advance the GPU sends a `DraftAdvanceCommand`, the CS-3 gateway translates it, runs it through
the in-process-patched worker onto the wafer, and returns `draft_len=16` candidate ids. v1 runs a
**passthrough** kernel (ids echoed) so the path is numerically checkable before the real decode kernel.

Two latency levers were settled this session:
1. **Backbone = in-process gRPC patch** (`--bridge inproc`): one `sdk_run_command` RPC per exchange
   drives a resident appliance (no FIFO/daemon). Fastest backbone (~5x vs FIFO at the driver side).
2. **d2h receive = batch** (`--recv-mode batch`, `VERB_EXCH`): one `receive(draft_len*south_wlts)`
   instead of 16 per-blob receives. d2h cost is **host-receive-bound, not kernel-emit-bound**, and
   batch receive works even on a per-step-emitting kernel (no on-chip staging) -> transfers to the
   real decode kernel. This is the single biggest latency win.

Full numeric tables + breakdowns live in ContextBase log `GOZQ9I8pOe` ("Gateway passthrough SerDe").

## Current state

Branch `lexu/toy-emit-recv-modes` (off main, **NOT merged, no PR yet**). 3 commits: `352843c`
(toy emit x receive 2x2 kernel+bench), `da6ebbe` (both receive modes as backbone options + inproc
e2e driver), `9c08e47` (run_e2e_inproc.sh). Local suite 64 passed. README updated with the
in-process reproduction recipe + arg tables.

**Real GPU verify service VALIDATED (2026-06-29)** — drove `driver_main --bridge inproc --appliance
real` against the real cluster verifier `10.22.28.100:32245` (not the co-located mock). Full
1000-round benchmark, 0 errors, service requested k=16.

Measured p50 (batch receive, real service):
| scope (measured at) | p50 ms | notes |
| --- | --: | --- |
| appliance ring (worker<->wafer) | 0.166 | h2d 0.045 + batch d2h ~0.12 |
| driver-side gw<->WSE (gateway) | 1.932 | pump.exchange; qps 514; dist n=1000 p90 2.215/p99 2.480/std 0.266 |
| **verify-side GPU<->WSE (GPU, BOTTOM-LINE)** | **3.296** | GPU's own bench: qps 301, p90 3.713, p99 4.129, avg 3.320 |

Per-step receive would be ring 2.71 / driver 4.69 / verify 6.23 ms -> batch is ~1.9x faster e2e.
Real verify-side 3.296 ~= earlier mock estimate 3.204 => **mock co-location was a wash, confirmed.**

Cumulative breakdown (batch, p50, wafer-outward): ring 0.166 -> +ping 0.96 = 1.126 -> +gw overhead
0.81 = driver 1.932 -> +GPU<->gw leg 1.36 = verify 3.296. **Biggest chunk = GPU<->gateway network
leg ~1.36 ms (41%, cross-cluster gRPC, NOT the wafer)**; leg-1 protobuf SerDe inside it only ~0.14
ms (gateway SerDe never the bottleneck); wafer trivial 0.166 ms (5%). ~66% of verify-side jitter
(p99-p50) originates gw<->WSE-side, not the network.

## Decisions

- Spec-dec default = **in-process patch + batch receive**. Both receive modes kept as first-class
  backbone options (`VERB_EXCH`=batch / `VERB_RECV_STREAM`=per-step; `driver_main --recv-mode`).
- Passthrough-SerDe transport = keep opt-in, do NOT default (device A/B was a near-wash; ~80us moves
  onto the pod). The real lever is gateway-CPU offload (throughput), not latency.
- Verify-side (GPU-measured) is the metric that matters (verifier idle time). To get its EXACT
  distribution / drop-warmup / per-round segment split, the GPU service must dump RAW per-round
  latencies (it currently emits only aggregate percentiles).

## Commands / paths

Code: `gala2:/home/lexu/nc_service`, sample at `waferengine/samples/specdec/`. CS-3 sync at
`~/rsync/nc_service-rsync/` (via `/cs3-runner` skill; SDK `csl` conda env; `export PYTHONPATH=.`).

```bash
# Driver-side + appliance ring, both receive modes, one bring-up (no GPU peer):
python waferengine/samples/specdec/emit_recv_bench.py \
  --config waferengine/samples/specdec/config/v0_emit_stream.json \
  --rounds 300 --ready-timeout 1800 --out-dir _runs/emit_stream

# E2E against the REAL GPU verifier (serve ALL 1000 so its benchmark PASSES + prints percentiles):
python waferengine/samples/specdec/driver_main.py --bridge inproc --appliance real \
  --recv-mode batch --config waferengine/samples/specdec/config/v0_emit_stream.json \
  --addr 10.22.28.100:32245 --draft-service-id <unique-id> --skip-reachability \
  --ready-timeout 1500 --draft-len 16 --idle-timeout 20 --out _runs/full_batch.json
```

## Open questions / next

- [ ] Get the GPU verify service to dump RAW per-round latencies -> exact verify-side distribution.
- [ ] Per-step full-1000 benchmark against the real service for a GPU-measured both-modes comparison.
- [ ] Real prefill+decode kernel swap-in (replaces the passthrough `build_layout` + `config/v0.json`).
- [ ] Decide branch disposition: merge `lexu/toy-emit-recv-modes` to main (PR being prepared, not opened).

## Pitfalls (cost time this session)

- **GPU verify-service benchmark is fixed at requests=1000, k=16.** It treats ANY draft-service
  disconnect before round 1000 as a FAILURE (`code=503 "draft service ... disconnected"`). So
  `--max-rounds N` with N<1000 ALWAYS fails its benchmark even though our N rounds were clean. Serve
  all 1000 + `--idle-timeout` for teardown. 503 "disconnected" = connection drop, NOT a bad response.
- **EIDF gateway rate-limit:** rapid cs3-ssh retries -> "Connection closed by UNKNOWN port 65535" for
  ~10-60 min. Stop ~30 min, one gentle probe; long device runs use `nohup setsid` detached + poll.
- **CSL:** `SOUTH`/`NORTH`/`EAST`/`WEST` are reserved direction keywords (name the const `SW`); `cslc`
  lexer is ASCII-only (no em-dash/x in comments); sim allows only ONE Simfabric per process.
- `--dump-timing` ring row is launcher-only (no `ring_ms` under `--bridge inproc`).

## Last updated

2026-06-29 15:29 BST
