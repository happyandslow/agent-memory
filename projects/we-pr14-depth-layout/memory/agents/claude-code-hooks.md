# Claude Code Hooks

Host: `gala2`
Work repo: `/home/lexu/we-pr14-depth-layout` (git worktree of `/home/lexu/WaferEngine-staging/.git`, branch `lexu/staging/decode-pipeline-depth`)
Memory repo: `/home/lexu/agent-memory`
Project memory path: `/home/lexu/agent-memory/projects/we-pr14-depth-layout`

## Installed hooks

- SessionStart: (none recorded yet)
- PreCompact: (none recorded yet)
- Stop: (none recorded yet — the memory repo's own `Stop` hook regenerates `timeline.md`/`index.md`)
- SubagentStop: (none recorded yet)

## Verification

```bash
cd /home/lexu/agent-memory
python3 scripts/check_memory_repo.py
```

## Notes

- Keep `.claude/settings.local.json` local if it contains absolute paths.
- Hooks should write curated memory, not raw transcript dumps.
- This project is a sibling worktree of `WaferEngine-staging`; do not run destructive `clean.sh -y`
  in the work repo without reading the full `-n` list (it deletes git-ignored `CLAUDE.md`).
