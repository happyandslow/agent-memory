# Trace KV economics and agentic workloads

- Claude Code transcript analysis must de-duplicate streaming assistant records by message id; corrected trace shape is 1,057 contexts, 46,650 calls, and 4,032 turns at the 2026-09-04 snapshot.
- Agentic calls are short individually but a user turn aggregates many calls and most tokens can be hidden reasoning; trace representativeness differs between Mooncake, Claude Code, ServeGen, and SWE-style workloads.
- Keep-vs-park is settled inside a turn by short gaps, but turn-boundary contention/concurrency remains unsettled. Compare against GPU+host-DRAM systems, not a lone GPU without host mirror.
- KV capacity across N wafers is proportional under the recorded placement rule, but 29K on one wafer fits almost none of the corrected Claude Code calls.
