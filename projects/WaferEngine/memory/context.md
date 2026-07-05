# WaferEngine Context

Compact startup packet for fresh agent sessions. Keep this short enough that an agent can read it every time.

## What this project is

- WaferEngine / WaferServe work around WSE-3 kernel resource analysis, especially PE-local SRAM and fabric resource limits for transformer decode/prefill kernels.

## Current state

- Active focus is the PE SRAM / fabric-resource breakdown for qwen3-1.7B decode + prefill on real CS-3/WSE-3.
- `tools/pe_mem_breakdown/` exists on branch `lexu/pe-mem-breakdown` (not merged as of latest memory). The topic note records device-measured per-PE memory use, max sequence length, and color usage.
- Human meeting note `human/2026-06-29-meeting-notes-waferos.md` adds a follow-up to collect session examples for on-chip KV cache and recompute/evict KV-cache behavior.

## Current focus

- Decide whether/how to use the PE-SRAM breakdown results in WaferOS/session examples.
- Resolve whether branch `lexu/pe-mem-breakdown` should be merged.

## Next likely actions

- [ ] Add session examples of keeping KV cache on chip, with pointers back to the PE-memory analysis.
- [ ] Add session examples of recompute/evict KV cache for wafer chips; source note references an Obsidian image not currently present in this repo.
- [ ] Decide whether to merge `lexu/pe-mem-breakdown`.
- [ ] Optional: run config sweeps (seq_len / layers-per-block) to quantify the sequence-length lever.

## Must-read topic notes

- `memory/topics/pe-sram-memory-breakdown.md` — device-measured PE SRAM breakdown, max sequence-length ceiling, color usage, commands, and pitfalls.

## Important constraints

- Verify live repo/server state before assuming branch status or result paths; memory is context, not proof.
- Do not store secrets or raw cluster credentials in agent-memory.
- The 22,784 max sequence-length result is compile/placement only at bsz=1, not a verified full inference run.

## Restart checklist

1. Verify live repo/server state; memory may be stale.
2. Read `tracking/status.md`.
3. Read `memory/topics/pe-sram-memory-breakdown.md`.
4. Check `human/2026-06-29-meeting-notes-waferos.md` if the task mentions WaferOS/session examples or KV-cache behavior.
5. Proceed with the user's task.
