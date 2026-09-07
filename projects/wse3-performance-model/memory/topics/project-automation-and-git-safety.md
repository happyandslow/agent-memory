# Project automation and Git safety

- Codex/Claude session lifecycle hooks should log starts/stops/precompact/subagent stops as pointers, not raw transcript stores.
- GitHub/local tracking was introduced after project creation; verify live repo state before relying on version metadata.
- Project-session safety: preserve staged/unstaged boundaries and make commit/prompt policy explicit before coding agents mutate Git state.
