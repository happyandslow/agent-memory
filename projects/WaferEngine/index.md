# WaferEngine

Obsidian landing page for `WaferEngine`.

## Quick links

- [[plan]] — human-maintained roadmap/progress narrative
- [[tracking/status]] — generated current-state dashboard
- [[memory/context]] — compact agent startup packet
- [[memory/project]] — stable project facts and repo paths
- [[memory/README]] — memory layout and policy

## Notes & artifacts

- [[memory/topics/pe-sram-memory-breakdown]] — per-PE SRAM breakdown (qwen3 decode+prefill, real WSE-3)
- `docs/2026-06-28-wse-per-pe-resource-discovery.md` — **discovery write-up** (memory + seq-len + colors, with image/commit traceability)
- `docs/wse_per_pe_resource_analysis.pptx` / `.pdf` — **summary slides** (10, non-expert); regen `docs/make_slides.py`
- `docs/2026-06-28-pe-sram-memory-breakdown-tool-design.md` — tool design spec
- `docs/2026-06-28-pe-sram-memory-breakdown-tool-plan.md` — tool implementation plan
- `memory/transcripts/2026-06-28-session-multi-request-brainstorm.md` — full session log

## Current status

See [[tracking/status]].

## How to start an agent session

```text
Use the agent-memory repo. Project: WaferEngine.
Read memory/context.md, memory/project.md, relevant topic notes, tracking/status.md, and plan.md. Then help me with: <task>.
```
