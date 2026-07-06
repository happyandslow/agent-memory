#!/usr/bin/env python3
"""Thin wrapper: delegates to the agent-memory skill's checker.

Kept at this path so existing `python3 scripts/check_memory_repo.py` calls
(cron, CLAUDE.md, HUMAN.md) continue to work after checker consolidation.
"""
from __future__ import annotations
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

def _skill_checker() -> Path | None:
    candidates = [
        Path(os.environ["AGENT_MEMORY_SKILL"]) / "scripts" / "check_memory_repo.py"
        if os.environ.get("AGENT_MEMORY_SKILL") else None,
        Path.home() / ".claude/skills/agent-memory/scripts/check_memory_repo.py",
        Path.home() / "Projects/claude-skills/agent-memory/scripts/check_memory_repo.py",
    ]
    return next((c for c in candidates if c and c.is_file()), None)

def main() -> int:
    skill = _skill_checker()
    if skill is None:
        print("agent-memory skill checker not found; install the skill "
              "(claude-skills/agent-memory/install.sh).", file=sys.stderr)
        return 2
    return subprocess.call(
        [sys.executable, str(skill), "--root", str(REPO_ROOT), *sys.argv[1:]]
    )

if __name__ == "__main__":
    raise SystemExit(main())
