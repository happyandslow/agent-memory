# we-pr14-depth-layout Project Memory

## Identity

- Project slug: `we-pr14-depth-layout`
- Human name: `WaferEngine PR14 decode depth/layout`
- Owner: Le Xu
- Area: `10-work/we-pr14-depth-layout`
- Confidentiality/access boundary: private (WaferEngine research context)

## Source of truth

- Code repo: git@github.com:happyandslow/WaferEngine.git (fork; branch
  `lexu/staging/decode-pipeline-depth`, base `93a6d0e`; 2026-08-06 CS-3 profile on
  upstream/main `b136ab64`)
- Remote server path(s): `gala2:/home/lexu/we-pr14-depth-layout` (worktree)
- Local checkout path(s):
- Obsidian path: `/Users/lexu/Library/CloudStorage/GoogleDrive-lxu5398@gmail.com/My Drive/Obsidian-note-vault/note-vault/10-work/we-pr14-depth-layout`
- Memory repo path, remote/gala2: `/home/lexu/agent-memory/projects/we-pr14-depth-layout`
- Memory repo path, Mac: `/Users/lexu/Projects/agent-memory/projects/we-pr14-depth-layout`
- Portable routing rule: in the work repo, resolve `$AGENT_MEMORY_ROOT`; otherwise use sibling
  `../agent-memory`; otherwise the Mac fallback `/Users/lexu/Projects/agent-memory`.

## Machines and agents

| Host | Role | Paths | Notes |
| --- | --- | --- | --- |
| gala2 | primary development | work repo `/home/lexu/we-pr14-depth-layout`; memory repo `/home/lexu/agent-memory` | Depth/layout worktree off the PR14 WaferEngine line. |
| MacBook | Obsidian/Hermes/local view | `/Users/lexu/Projects/agent-memory/projects/we-pr14-depth-layout` | |
| Mac mini | backup | | Clone/pull memory repo only if needed. |

## Commands

### Build/test/check

```bash
# fill in — decode pipeline-depth bench lives under
#   models/qwen3_1p7b-decode/bench/  (results/ holds device-authoritative runs)
```

### Status update

```bash
export MEMORY=$AGENT_MEMORY_ROOT/projects/we-pr14-depth-layout   # or /home/lexu/agent-memory/...
```

## Conventions

- Device TSC at 0.85 GHz is authoritative; local SDK-2.10 sim runs check completion/routing only
  and are NOT byte-identical to CS-3 1.13.2 device artifacts.
- Never report the nominal-depth pipelined-prefill product (per-stage tok/s x n_stages) as
  achieved throughput — it is an upper bound until an actual pipelined-prefill run exists.

## Known pitfalls

- `SdkLauncher.run()` does not retain worker files; `download_artifact()` before leaving the
  launcher context. CS-3 sync deletion can drop git-ignored remote results — copy device results
  locally first. (See [[decode-pipeline-depth-layout]] § Reusable execution lessons.)

## Important links

- Primary report: `docs/DECODE_PIPELINE_DEPTH_EXPERIMENT_2026-08-05.md` (work repo)
- ContextBase log:
  https://context.ed-aisys.com/doc/2026-08-06-result-qwen3-17b-decode-pipeline-depth-profile-tWZ5gVLrVO
- Topic: [[decode-pipeline-depth-layout]]
