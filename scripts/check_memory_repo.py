#!/usr/bin/env python3
"""Validate the agent-memory repository structure.

This intentionally checks structure only. It does not judge content quality.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECTS = ROOT / "projects"

ROOT_REQUIRED = [
    "README.md",
    "AGENTS.md",
    "CLAUDE.md",
    "HERMES.md",
    "HUMAN.md",
    ".gitignore",
]

PROJECT_REQUIRED = [
    "index.md",
    "plan.md",
    "tracking/status.md",
    "memory/README.md",
    "memory/project.md",
    "memory/context.md",
    "memory/topics/README.md",
    "memory/transcripts/README.md",
    "memory/inbox/README.md",
    "memory/agents/README.md",
]

FORBIDDEN_SUFFIXES = {
    ".db",
    ".sqlite",
    ".sqlite3",
    ".pem",
    ".key",
    ".p12",
}

FORBIDDEN_NAMES = {
    ".env",
    "id_rsa",
    "id_ed25519",
}


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def check_required() -> list[str]:
    errors: list[str] = []
    for item in ROOT_REQUIRED:
        path = ROOT / item
        if not path.exists():
            errors.append(f"missing root file: {item}")

    if not PROJECTS.exists():
        errors.append("missing projects/ directory")
        return errors

    project_dirs = [p for p in PROJECTS.iterdir() if p.is_dir() and not p.name.startswith(".")]
    if not project_dirs:
        errors.append("projects/ contains no project directories")
        return errors

    for project in sorted(project_dirs):
        for item in PROJECT_REQUIRED:
            path = project / item
            if not path.exists():
                errors.append(f"missing project file: {rel(path)}")
    return errors


def check_forbidden_files() -> list[str]:
    errors: list[str] = []
    for path in ROOT.rglob("*"):
        if ".git" in path.parts:
            continue
        if not path.is_file():
            continue
        lower = path.name.lower()
        if lower in FORBIDDEN_NAMES or any(lower.endswith(s) for s in FORBIDDEN_SUFFIXES):
            errors.append(f"potential secret/database file should not be committed: {rel(path)}")
    return errors


def main() -> int:
    errors = check_required() + check_forbidden_files()
    print(f"agent-memory check @ {datetime.now(timezone.utc).isoformat()}")
    print(f"root: {ROOT}")
    if errors:
        print("FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
