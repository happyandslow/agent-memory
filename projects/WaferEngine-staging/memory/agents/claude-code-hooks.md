# Claude Code Hooks

Host: `<host>`
Work repo: `gala2:/home/lexu/WaferEngine-staging`
Memory repo: `/Users/lexu/Projects/agent-memory`
Project memory path: `/Users/lexu/Projects/agent-memory/projects/WaferEngine-staging`

## Installed hooks

- SessionStart: 
- PreCompact: 
- Stop: 
- SubagentStop: 

## Verification

```bash
cd /Users/lexu/Projects/agent-memory
python3 scripts/check_memory_repo.py
```

## Notes

- Keep `.claude/settings.local.json` local if it contains absolute paths.
- Hooks should write curated memory, not raw transcript dumps.
- Hook failures should not block Claude Code, but Hermes cron should detect stale memory.
