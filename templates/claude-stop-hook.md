# Claude Code Stop hook for agent-memory (per work repo)

Add to `.claude/settings.local.json` (gitignored) on machines with a checkout.
Fires at the end of each response turn; gated on `projects` having any pending
changes (tracked or untracked) so ordinary turns are no-ops.
Regenerates deterministic views and commits LOCALLY (no push).

Note: the `$HOME/agent-memory` fallback matches the sibling-clone layout; on
hosts using a different path (e.g. `~/repos/agent-memory`), setting
`AGENT_MEMORY_ROOT` is required — otherwise the hook silently no-ops.

```json
{
  "hooks": {
    "Stop": [{"hooks": [{"type": "command", "command": "bash -lc 'R=\"${AGENT_MEMORY_ROOT:-$HOME/agent-memory}\"; cd \"$R\" || exit 0; [ -z \"$(git status --porcelain -- projects)\" ] && exit 0; python3 \"$HOME/.claude/skills/agent-memory/scripts/build_views.py\" --root \"$R\"; git add projects && git commit -q -m \"memory: regen views (session hook)\" || true'"}]}]
  }
}
```
