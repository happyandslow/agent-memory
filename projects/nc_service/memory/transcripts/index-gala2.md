# Transcript Index — gala2 (Claude Code)

Compact pointers to meaningful sessions on the gala2 dev host. Raw transcripts stay local under
`~/.claude/projects/-home-lexu-nc-service/`; this is an index only.

| date | agent/tool | topic | outcome | memory updated |
| --- | --- | --- | --- | --- |
| 2026-06-29 | Claude Code (gala2) | SpecDec d2h latency + **real GPU verify-side** | Drove `--bridge inproc --appliance real` vs the real cluster verifier `10.22.28.100:32245`; full 1000-round batch, 0 errors. GPU-measured **verify-side p50 3.30 ms**; driver-side 1.93 ms. Full cumulative breakdown + distribution; diagnosed the "benchmark failed" as `--max-rounds`<1000 early disconnect. README in-process recipe added. Branch `lexu/toy-emit-recv-modes` prepped for PR (not opened). | `context.md`, `topics/specdec-d2h-latency.md`, `tracking/status.md`; ContextBase `GOZQ9I8pOe` rev 23 |

Source raw transcript (local only): `~/.claude/projects/-home-lexu-nc-service/b717d4ff-e9c4-4542-8948-63f9aeab7f45.jsonl` (+ continuation session).
