# Remote Claude Code Hook Template

Use this as a starting point for a work repo on a remote SSH server.

Assumed layout:

```text
~/repos/<work-project>/
~/repos/agent-memory/
```

Example `.claude/settings.local.json` shape:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "cd ~/repos/agent-memory && python3 scripts/check_memory_repo.py > /tmp/agent-memory-check.log 2>&1 || true"
          }
        ]
      }
    ],
    "PreCompact": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "cd ~/repos/agent-memory && git status --short > /tmp/agent-memory-status.log 2>&1 || true"
          }
        ]
      }
    ]
  }
}
```

Prefer project-specific scripts that update curated memory before committing. Keep this file local if it contains absolute paths or host-specific details.
