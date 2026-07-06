# WaferEngine-staging Context

Compact startup packet for fresh agent sessions. Keep this short enough that an agent can read it every time.

## What this project is

- Host-side LLM inference engine + Cerebras WSE-3 CSL kernels. Active model = **Qwen3-1.7B** as four deployments under `models/qwen3_1p7b-*`: `-decode`, `-prefill`, `-e2e` (prefill+decode fused on one chip, on-chip KV relay), `-e2e-pdSeparate` (PD-disaggregation: prefill & decode as separate artifacts, KV bridged through host DRAM).
- Runs on real WSE-3 (EPCC CS-3 cluster via `/cs3-runner`) or local `simfab`.

## Current state (2026-07-06 — from memory notes, not live repo recheck)

- **e2e fused**: first CS-3 device PASS (mock weights) — `wsjob-dhpbbq2k…`, compile 291s / run 6.9s, 2240 tok/s decode. Pipeline correct on mock weights.
- **pdSeparate**: CS-3 compile **FAIL** — prefill.csl per-PE SRAM overflow at the shipped large-context config (regressed vs an uncommitted prior pass).
- **Real Qwen3 weights: NOT wired** in any model (mock/seeded only). Deferred.
- Max context (pdSeparate, 2×2 layout): total ≈ 4096 but **prompt capped ≈ 512 tokens** (prefill quadratic score buffer is the binding limit; decode ~7–8K).
- KV-policy analysis now frames preserve/evict as a tier ladder: T0 in-place, T0.5 in-bank multi-request reuse, T1 idle-PE SRAM offload, T2 host-DRAM offload, T3 evict+recompute.

## Current focus

- KV preserve-vs-evict / offload-tier policy tradeoffs across the two deployments (Le's main interest) — see `memory/topics/kv-cache-policy-tradeoffs.md`.
- For multi-turn reuse with a large warm history and small new turn, the likely WSE-specific direction is **force-decode-in-place** rather than shipping decode KV back to prefill; the reverse decode→prefill bridge does not exist.

## Next likely actions

Use `tracking/status.md` for the canonical checkbox list. In short: quantify T1 idle-PE offload, scope forced-token decode and T0.5 in-bank reuse, unblock pdSeparate long-context prefill by shrinking/removing the quadratic buffer, and leave real HF weights/tokenizer/oracle as deferred.

## Must-read topic notes

- `memory/topics/kv-cache-policy-tradeoffs.md` — core preserve/evict/offload analysis, including tiering, force-decode-in-place, and breakeven method.
- `memory/topics/e2e-pdSeparate-device-validation.md` — device results, weights gap, max-context byte model.
- `memory/topics/standalone-vs-integrated-kernel-parity.md` — what integrated e2e/pdSeparate lack vs up-to-date standalone decode/prefill (multi-request, varlen, chunked prefill, EOS, #12 softmax, oracles).
- `memory/topics/agentic-kv-trace-datasets.md` — trace/dataset pointers for KV preserve-vs-evict / request-length / tool-overhead analysis.

## Important constraints

- 48 KB/PE SRAM; weights (layers/block) dominate. `arch=wse3`.
- CS-3 shared account `congjiehe`; jobs identified by workflow id, not USER.
- Integrated e2e/pdSeparate have no multi-round loop; standalone decode multi-round isolates requests and reloads KV from host, but does not reuse KV content today.

## Restart checklist

1. Verify live repo/server state; memory may be stale.
2. Read `tracking/status.md` + the topic notes above.
3. Proceed with the user's task.
