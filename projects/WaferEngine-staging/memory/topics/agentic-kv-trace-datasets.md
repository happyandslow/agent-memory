# Agentic KV-Cache Trace Datasets

## Summary

Datasets/traces for analyzing the **KV-cache preserve-vs-evict tradeoff** on
*real agentic workloads* — where LLM calls and tool calls are recorded with
timing. Target metrics for this analysis: request lengths (input/output token
distributions), KV sharing % (prefix reuse), and tool-call overhead (idle gaps
where eviction decisions bite).

Context: `ScaleAI/MCP-Atlas` (HF) was evaluated and **rejected** — it records
the canonical tool-call trajectory but has **no timestamps/latencies**, so it
cannot measure tool-call overhead or idle gaps. Fields: TASK, ENABLED_TOOLS
(10–25), PROMPT, GTFA_CLAIMS (claims-coverage rubric), TRAJECTORY. 500-task
sample of a 36-server/220-tool benchmark; useful for tool-use eval, not serving.

## Current state

Shortlist identified (ranked by fit); not yet cloned/analyzed.

## Decisions

Recommended plan: use **TraceLab** for the full agentic timeline; use the
**Mooncake tool&agent trace** as a clean second source for prefix-sharing %
(hash_ids make KV-sharing computable without any inference); read
**CacheTTL/Continuum** for the preserve-vs-evict methodology framing.

## Datasets

### 1. TraceLab — closest fit (agentic: LLM steps + tool calls + timing + cache)
- Purpose-built: "Characterizing Coding Agent Workloads for LLM Serving."
- Scale: ~4,300 coding-agent sessions, ~350K LLM steps, ~430K tool calls.
- Source: real **Claude Code + Codex** usage. License CC-BY-4.0.
- Records LLM steps *and* tool calls with timing; analyzes prefix-cache hit
  rates and tool-call overhead directly.
- Shape: long contexts / short outputs, long autonomous loops, heavy-tailed
  tool calls, "high but imperfect prefix cache hit rates."
- Findings flagged: lower-overhead tool calling, append-length-aware prefill,
  semantic-aware tool-latency prediction, KV mgmt around human-paced gaps.
- Access: https://github.com/uw-syfi/TraceLab · https://tracelab.cs.washington.edu
- Paper: https://arxiv.org/abs/2606.30560v1

### 2. Mooncake request traces — standard for KV-reuse simulation
- Kimi/Moonshot, FAST'25. Three traces: conversation, **tool&agent**, synthetic.
- Files: `FAST25-release/traces/` (e.g. `mooncake_trace.jsonl`).
- Per-record schema (JSONL):
  `{"timestamp": <arrival_ms>, "input_length": N, "output_length": M, "hash_ids": [block ids...]}`
- `hash_ids` = per-KV-block hash combining block content + prefix hash → shared
  prefixes share leading hash_ids ⇒ **exact prefix-sharing % computable from the
  trace, no inference needed**. Block = 512 tokens default.
- Published prefix-cache ratios: **conversation ~40%, tool&agent ~59%** (long
  repetitive system prompts). Use the **tool&agent** trace.
- Caveat: request-level with arrival timestamps, NOT per-step LLM-vs-tool span
  timeline; tool-call overhead only implicit as inter-request arrival gaps.
- Access: https://github.com/kvcache-ai/Mooncake · paper https://arxiv.org/pdf/2407.00079

### 3. Systems papers doing this exact tradeoff
- **CacheTTL / Continuum** (arXiv 2511.02230) — "KV Cache Time-to-Live" for
  multi-turn agent scheduling; parses tool calls, tracks per-tool latency from
  inter-request intervals, computes TTL to preserve-vs-evict during the tool-call
  gap. Literally this tradeoff. Traces + testbed stated to be open-sourcing.
- **CacheWise** (arXiv 2606.16824) — KVCache mgmt for serving coding agents.
- **DualMap** (arXiv 2602.06502) — cache affinity vs load balancing (distributed).

## Open questions

- Are TraceLab per-step fields granular enough to separate LLM-call time from
  tool-execution time cleanly? (verify by inspecting the actual records)
- Has CacheTTL/Continuum released its trace yet?

## Last updated

2026-07-05
