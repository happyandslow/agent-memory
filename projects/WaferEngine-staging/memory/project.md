# WaferEngine-staging Project Memory

## Identity

- Project slug: `WaferEngine-staging`
- Human name: `WaferEngine-staging`
- Owner: Le Xu
- Area: `10-work/WaferEngine-staging`
- Confidentiality/access boundary: 

## Source of truth

- Code repo: git@github.com:happyandslow/WaferEngine.git
- Remote server path(s): gala2:/home/lexu/WaferEngine-staging
- Local checkout path(s): 
- Obsidian path: `/Users/lexu/Library/CloudStorage/GoogleDrive-lxu5398@gmail.com/My Drive/Obsidian-note-vault/note-vault/10-work/WaferEngine-staging`
- Memory repo path: `/Users/lexu/Project/agent-memory/projects/WaferEngine-staging`

## Machines and agents

| Host | Role | Paths | Notes |
| --- | --- | --- | --- |
| remote | primary development |  |  |
| MacBook | Obsidian/Hermes/local view | `/Users/lexu/Project/agent-memory/projects/WaferEngine-staging` |  |
| Mac mini | backup |  |  |

## Commands

### Build/test/check

```bash
# Local simulator run (needs Cerebras SDK env: cs_python/cslc)
cd models/qwen3_1p7b-decode && ./run_sim.sh model_config/test_sim_2x2block_kv_varlen.json
# Host-only unit tests (no wafer)
pytest waferengine/ gpu_reference/
# CS-3 device run: prefer the /cs3-runner skill (gateway -> rsync -> timeout-guarded)
#   run_device.sh <cfg> is the direct SdkLauncher path (self-allocates appliance)
```

### Status update

```bash
export MEMORY=$AGENT_MEMORY_ROOT/projects/WaferEngine-staging   # or /home/lexu/agent-memory/...
```

## Conventions

- Active model = `models/qwen3_1p7b-*` (decode/prefill/e2e/e2e-pdSeparate). Old
  llama3_1_8b is deprecated (`models/deprecated/`); README/REPO_LAYOUT docs describe
  it and are stale — trust the qwen `launch.py` + `run_sim.sh`/`run_device.sh` pattern.
- Config naming: `test_sim_*` → simulator, `test_device_*` → real WSE-3.
- Weights are **mock/seeded random** on the device path (no real HF weights yet).

## Known pitfalls

- **Real Qwen3 weights are NOT wired** into any model — mock/seeded only; no HF
  loader, no Qwen3 gpu_reference oracle, no tokenizer. See
  [[e2e-pdSeparate-device-validation]].
- **pdSeparate `test_device_2x2blk_kv` does not compile** on the committed tree —
  prefill.csl overflows per-PE SRAM at PREFILL_LEN=2048 (the STATUS.md "pass" was
  uncommitted). Prompt cap ≈ 512 tokens at the 2×2/7-layer layout.
- Device configs' `FILES_TO_STAGE` in `launch_device.py` is a FIXED list — a new
  `.csl` not added → `FATAL: Could not find source code` at compile.
- CS-3 via `/cs3-runner`: shared account `congjiehe` — identify own jobs by
  workflow id, NOT USER (`cancel-mine` would kill other tenants). Warm-gateway
  window can lapse mid-run (transient `Permission denied (publickey)` → re-check + retry).

## Important links

- InferCept (KV preserve/swap/discard cost policy): <https://arxiv.org/abs/2402.01869>
- Topic: [[kv-cache-policy-tradeoffs]], [[e2e-pdSeparate-device-validation]]
