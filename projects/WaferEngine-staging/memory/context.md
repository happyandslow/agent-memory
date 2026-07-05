# WaferEngine-staging Context

Compact startup packet for fresh agent sessions. Keep this short enough that an agent can read it every time.

## What this project is

- Host-side LLM inference engine + Cerebras WSE-3 CSL kernels. Active model =
  **Qwen3-1.7B** as four deployments under `models/qwen3_1p7b-*`: `-decode`,
  `-prefill`, `-e2e` (prefill+decode fused on one chip, on-chip KV relay),
  `-e2e-pdSeparate` (PD-disaggregation: prefill & decode as separate artifacts,
  KV bridged through host DRAM).
- Runs on real WSE-3 (EPCC CS-3 cluster via `/cs3-runner`) or local `simfab`.

## Current state (2026-07-05)

- **e2e fused**: first-ever CS-3 device PASS (mock weights) — `wsjob-dhpbbq2k…`,
  compile 291s / run 6.9s, 2240 tok/s decode. Pipeline correct on mock weights.
- **pdSeparate**: CS-3 compile **FAIL** — prefill.csl per-PE SRAM overflow at the
  shipped large-context config (regressed vs an uncommitted prior pass).
- **Real Qwen3 weights: NOT wired** in any model (mock/seeded only). Deferred.
- Max context (pdSeparate, 2×2 layout): total ≈ 4096 but **prompt capped ≈ 512
  tokens** (prefill quadratic score buffer is the binding limit; decode ~7–8K).

## Current focus

- KV preserve-vs-evict / offload-tier policy tradeoffs across the two deployments
  (Le's main interest) — see [[kv-cache-policy-tradeoffs]].

## Next likely actions

- [ ] Quantify idle-PE (on-fabric) KV offload cost vs host-DRAM offload.
- [ ] Fix pdSeparate prefill SRAM overflow (taller layout / trim quadratic buffer)
      to enable long-context PD.
- [ ] (Deferred) wire real HF weights + tokenizer + Qwen3 oracle for real inference.

## Must-read topic notes

- `memory/topics/kv-cache-policy-tradeoffs.md` — the core preserve/evict/offload analysis.
- `memory/topics/e2e-pdSeparate-device-validation.md` — device results, weights gap, max-context byte model.
- `memory/topics/agentic-kv-trace-datasets.md` — when sourcing real agentic traces for KV preserve-vs-evict / request-length / tool-overhead analysis (pointer; note may not exist yet).

## Important constraints

- 48 KB/PE SRAM; weights (layers/block) dominate. `arch=wse3`.
- CS-3 shared account `congjiehe`; jobs identified by workflow id, not USER.

## Restart checklist

1. Verify live repo/server state; memory may be stale.
2. Read `tracking/status.md` + the topic notes above.
3. Proceed with the user's task.
