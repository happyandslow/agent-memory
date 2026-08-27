# Claude Code Hooks

Host: `gala2`
Work repo: `/home/lexu/wse3-performance-model`
Memory repo: `/home/lexu/agent-memory`
Project memory path: `/home/lexu/agent-memory/projects/wse3-performance-model`

## Installed hooks

- SessionStart: not configured as of 2026-08-27
- PreCompact: not configured as of 2026-08-27
- Stop: not configured as of 2026-08-27
- SubagentStop: not configured as of 2026-08-27

## Verification

```bash
cd /home/lexu/agent-memory
python3 scripts/check_memory_repo.py
```

## Notes

- Keep `.claude/settings.local.json` local if it contains absolute paths.
- Hooks should write curated memory, not raw transcript dumps.
- Hook failures should not block Claude Code, but Hermes cron should detect stale memory.
