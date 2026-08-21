# csl-knowledge MCP blocked in non-interactive sessions — KB is on disk — 2026-08-20

**Project:** WaferEngine-staging
**Author:** claude
**Status:** drained 2026-08-21 into `memory/topics/csl-control-payload-mechanisms.md`, `plan.md`, and promotion follow-up in `tracking/conflicts.md`

## What happened / finding

- Situation: a non-interactive worker session (dispatched implementation agent, headless run) needs CSL/SDK facts — switch semantics, control-wavelet encoding, stdlib source — and calls the `csl-knowledge` MCP tools, but the read tools come back **permission-blocked** (in one session only `search_docs` responded). The agent stalls on research it cannot complete via MCP.
- Workaround, validated independently by two M3 Phase-A worker sessions on 2026-08-20: the same knowledge base lives on local disk at `/home/lexu/CSL-Demo-Code/versions/v2.10/` (version-routed under `versions/v<X.Y>/`). Grep/Read it directly — e.g. the stdlib sources `control.csl` and `switch_config.csl` that decide switch/pop realizability are readable there without any MCP call.
- Both workers burned time re-deriving this path from scratch; neither found it recorded anywhere.
- Procedural and recurring across sessions → promotion candidate: a one-line note in the dispatch prompt for non-interactive workers ("if csl-knowledge MCP is blocked, read the KB at /home/lexu/CSL-Demo-Code/versions/v<X.Y>/") or a skill-level fallback would remove the rediscovery cost.

## Implications / next actions

- [ ] Consider adding the disk-path fallback to worker dispatch prompts or the csl-knowledge usage guidance (promotion — propose to Le, do not install).

## Pointers

- `/home/lexu/CSL-Demo-Code/versions/v2.10/` (on-disk KB root)
- Transcripts: `-home-lexu-WaferEngine-staging/53e9951a-*` and `95ca3777-*` (both M3/S0 Phase-A workers)
