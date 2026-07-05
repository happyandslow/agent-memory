#!/usr/bin/env python3
"""Initialize a new project memory folder from projects/_template.

Example:
  python3 scripts/init_project.py my-project \
    --name "My Project" \
    --code-repo git@github.com:org/my-project.git \
    --remote-path user@server:/path/to/my-project \
    --link-obsidian
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "projects" / "_template"
PROJECTS = ROOT / "projects"
OBSIDIAN_WORK = Path(
    "/Users/lexu/Library/CloudStorage/GoogleDrive-lxu5398@gmail.com/My Drive/Obsidian-note-vault/note-vault/10-work"
)

TEXT_SUFFIXES = {".md", ".txt", ".json", ".yaml", ".yml"}


def replace_in_file(path: Path, replacements: dict[str, str]) -> None:
    if path.suffix not in TEXT_SUFFIXES:
        return
    text = path.read_text()
    original = text
    for old, new in replacements.items():
        text = text.replace(old, new)
    if text != original:
        path.write_text(text)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a project memory scaffold")
    parser.add_argument("slug", help="project slug, e.g. llm-serving-paper")
    parser.add_argument("--name", default=None, help="human project name")
    parser.add_argument("--code-repo", default="", help="code repo URL or path")
    parser.add_argument("--remote-path", default="", help="primary remote work repo path")
    parser.add_argument("--local-path", default="", help="local work repo checkout path")
    parser.add_argument("--link-obsidian", action="store_true", help="create/update Obsidian 10-work/<slug> symlink")
    args = parser.parse_args()

    slug = args.slug.strip()
    if not slug or "/" in slug or slug in {".", "..", "_template"}:
        print(f"invalid project slug: {slug!r}", file=sys.stderr)
        return 2

    name = args.name or slug.replace("-", " ").replace("_", " ").title()
    dest = PROJECTS / slug
    if dest.exists():
        print(f"project already exists: {dest}", file=sys.stderr)
        return 1

    if not TEMPLATE.exists():
        print(f"missing template directory: {TEMPLATE}", file=sys.stderr)
        return 1

    shutil.copytree(TEMPLATE, dest)

    replacements = {
        "<project-slug>": slug,
        "<Project Name>": name,
        "<path-to-agent-memory>": str(ROOT),
        "<Project>": name,
        "<path>": args.remote_path or args.local_path or "",
    }
    for path in dest.rglob("*"):
        if path.is_file():
            replace_in_file(path, replacements)

    project_md = dest / "memory" / "project.md"
    text = project_md.read_text()
    if args.code_repo:
        text = text.replace("- Code repo: ", f"- Code repo: {args.code_repo}")
    if args.remote_path:
        text = text.replace("- Remote server path(s): ", f"- Remote server path(s): {args.remote_path}")
    if args.local_path:
        text = text.replace("- Local checkout path(s): ", f"- Local checkout path(s): {args.local_path}")
    project_md.write_text(text)

    obsidian_target = OBSIDIAN_WORK / slug
    if args.link_obsidian:
        OBSIDIAN_WORK.mkdir(parents=True, exist_ok=True)
        if obsidian_target.exists() or obsidian_target.is_symlink():
            print(f"Obsidian target already exists, not replacing: {obsidian_target}")
        else:
            obsidian_target.symlink_to(dest, target_is_directory=True)
            print(f"linked Obsidian: {obsidian_target} -> {dest}")

    print(f"created project memory: {dest}")
    print("\nAdd this portable routing block to the work repo AGENTS.md/CLAUDE.md/HERMES.md:\n")
    print(f"""## Project memory\n\nThis repo uses the shared `agent-memory` repository for durable project context.\n\nProject slug: `{slug}`\n\nResolve the memory repo root on the current machine in this order:\n\n1. If `$AGENT_MEMORY_ROOT` is set, use that.\n2. Else if `../agent-memory` exists next to this work repo, use `../agent-memory`.\n3. Else on Le's Mac, use `/Users/lexu/Projects/agent-memory`.\n\nThen the project memory is:\n\n```text\n$AGENT_MEMORY_ROOT/projects/{slug}\n```\n\nMachine-specific known locations:\n\n- Mac local memory repo: `/Users/lexu/Projects/agent-memory`\n- Mac Obsidian view: `{obsidian_target}`\n- Remote/server memory repo: set `$AGENT_MEMORY_ROOT` or clone as a sibling `../agent-memory`\n\nAt session start, read from the resolved project memory path:\n\n1. `memory/context.md`\n2. `memory/project.md`\n3. relevant files under `memory/topics/`\n4. `tracking/status.md`\n5. `plan.md` when planning or reporting status\n\nBefore writing memory, read the agent-memory write-contract (see the agent-memory skill).\n\nAt session wrap-up, update curated memory and commit changes in the memory repo.\nUse dated filenames for new artifacts: project docs files should be `YYYY-MM-DD-<slug>.<ext>`, and quick captures should be `memory/inbox/YYYY-MM-DD-<topic>.md`. Keep stable control files (`plan.md`, `tracking/status.md`, `memory/context.md`, `memory/project.md`) at their fixed names but put dated sections inside them for time-sensitive updates.\nDo not commit secrets, live databases, or bulk raw transcripts.\n""")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
