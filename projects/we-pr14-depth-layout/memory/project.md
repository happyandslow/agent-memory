# we-pr14-depth-layout Project Memory

## Identity

- Project slug: `we-pr14-depth-layout`
- Human name: `WaferEngine PR14 decode depth/layout`
- Owner: Le Xu
- Area: `10-work/we-pr14-depth-layout`
- Confidentiality/access boundary: private (WaferEngine research context)

## Source of truth

- Code repo: `git@github.com:happyandslow/WaferEngine.git` (remote `origin`)
- Local checkout path(s): `gala2:/home/lexu/we-pr14-depth-layout` — a **git worktree** whose
  `.git` points at `/home/lexu/WaferEngine-staging/.git/worktrees/we-pr14-depth-layout`, on branch
  `lexu/staging/decode-pipeline-depth` (HEAD `b136ab6`, off upstream/main). The **baseline** 8-stage
  layout compiles from a **sibling worktree** `/home/lexu/we-pr14-depth-baseline` (per
  `models/qwen3_1p7b-decode/bench/README.md`); each layout builds from its own tree so baseline
  configs never build candidate CSL. The 2026-08-05 rectangular-layout work in the drained captures
  was at base `93a6d0e`; the branch has since advanced to `b136ab6`. No separate Mac checkout.
- Remote server path(s): `gala2:/home/lexu/we-pr14-depth-layout` (this worktree is the remote/gala2
  copy). CS-3 device runs go through the launcher per the WaferEngine `/cs3-runner` convention.
- Obsidian path: `/Users/lexu/Library/CloudStorage/GoogleDrive-lxu5398@gmail.com/My Drive/Obsidian-note-vault/note-vault/10-work/we-pr14-depth-layout`
- Memory repo path, remote/gala2: `/home/lexu/agent-memory/projects/we-pr14-depth-layout`
- Memory repo path, Mac: `/Users/lexu/Projects/agent-memory/projects/we-pr14-depth-layout`
- Portable routing rule: in the work repo, resolve `$AGENT_MEMORY_ROOT`; otherwise use sibling
  `../agent-memory`; otherwise the Mac fallback `/Users/lexu/Projects/agent-memory`.

## Machines and agents

| Host | Role | Paths | Notes |
| --- | --- | --- | --- |
| gala2 | primary development | candidate worktree `/home/lexu/we-pr14-depth-layout` + baseline worktree `/home/lexu/we-pr14-depth-baseline`; memory repo `/home/lexu/agent-memory` | Both worktrees share `/home/lexu/WaferEngine-staging/.git`. Sibling layout makes `../agent-memory/projects/we-pr14-depth-layout` valid from the work repo. |
| MacBook | Obsidian/Hermes/local view | `/Users/lexu/Projects/agent-memory/projects/we-pr14-depth-layout` | |
| Mac mini | backup | | Clone/pull memory repo only if needed. |

## Commands

### Build/test/check

There is **no single canonical build command** — the project follows the standard WaferEngine
per-model pattern (`run_sim.sh` / `run_device.sh` + `launch*.py`), plus a dedicated
decode-pipeline-depth harness under `models/qwen3_1p7b-decode/bench/`. Truthful entry points
(paths are in the work repo, not this memory repo):

```bash
# All commands from the work repo /home/lexu/we-pr14-depth-layout .
# Local simulator smoke test (needs the Cerebras SDK env: cs_python/cslc); test_*.json only:
cd models/qwen3_1p7b-decode && ./run_sim.sh model_config/<test_*.json>

# CS-3 device run (SdkLauncher; prefer the /cs3-runner skill for gateway->rsync->timeout-guard):
cd models/qwen3_1p7b-decode && ./run_device.sh <device_config.json>

# Decode pipeline-depth profiling harness (baseline_8stage_256x256 vs rect_28stage_64x256):
#   models/qwen3_1p7b-decode/bench/ — layouts.py, gen_configs.py, capacity_search.py /
#   remote_capacity_search.py, grid_search.py, aggregate.py, run_manifest.py; results/ holds
#   device-authoritative runs; bench/tests/ holds the harness unit tests. See bench/README.md.
#   Primary metric = raw device TSC cycles/token; tok/s = 0.85e9 / cycles_per_token; bsz=1.
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
