# Claude Code Stop hook for agent-memory (per work repo)

Add to `.claude/settings.local.json` (gitignored) on machines with a checkout.
Fires at the end of each response turn; git-diff-gated so ordinary turns are no-ops.
Regenerates deterministic views and commits LOCALLY (no push).

```json
{
  "hooks": {
    "Stop": [{"hooks": [{"type": "command", "command": "bash -lc 'R=\"${AGENT_MEMORY_ROOT:-$HOME/agent-memory}\"; cd \"$R\" || exit 0; git diff --quiet -- projects && exit 0; python3 \"$HOME/.claude/skills/agent-memory/scripts/build_views.py\" --root \"$R\"; git add projects && git commit -q -m \"memory: regen views (session hook)\" || true'"}]}]
  }
}
```
