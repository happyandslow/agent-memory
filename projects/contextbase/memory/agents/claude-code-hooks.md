# Claude Code Hooks

Host: `<host>`
Work repo: `<path>`
Memory repo: `<path-to-agent-memory>`
Project memory path: `<path-to-agent-memory>/projects/contextbase`

## Installed hooks

- SessionStart:
- PreCompact:
- Stop:
- SubagentStop:

## Verification

```bash
cd <path-to-agent-memory>
python3 scripts/check_memory_repo.py
```

## Notes

- Keep `.claude/settings.local.json` local if it contains absolute paths.
- Hooks should write curated memory, not raw transcript dumps.
- Hook failures should not block Claude Code, but Hermes cron should detect stale memory.
