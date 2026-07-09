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
- Memory repo path: `/Users/lexu/Projects/agent-memory/projects/WaferEngine-staging`

## Machines and agents

| Host | Role | Paths | Notes |
| --- | --- | --- | --- |
| remote | primary development |  |  |
| MacBook | Obsidian/Hermes/local view | `/Users/lexu/Projects/agent-memory/projects/WaferEngine-staging` |  |
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

- **Simulator is for SMALL `test_sim_*` configs only (≤ 16×16 PE block region — the
  dim=64 toy configs). Anything larger / real-size MUST run on the actual CS-3
  device (`test_device_*`).** Reason: e2e `launch.py` runs simfab with
  `SimfabConfig(dump_core=True)` (dumps full device state) and `SIMFAB_TRACE` can
  add csviz traces — each sim run writes **tens–hundreds of GB**; a batch of
  parallel runs filled `/home` from 85%→94% and had to be killed + cleaned. So:
  **profiling / bandwidth / any many-PE run → device, not sim.** Sim stays for
  quick correctness checks on the toy configs only. (2026-07-06 directive from Le.)
- **Validate on CS-3, NOT the local simulator — even for small configs** (2026-07-07
  directive from Le). Local sim is only for *kernel debugging with trace dumps*.
  Reason beyond disk: the **local sim is SDK 2.10**, which emits `src dest operand
  overlap` warnings and can **`signal 11`-abort** on the KV-transfer's **benign
  element-wise in-place ops** (`prefill.csl` RoPE/SiLU/QK-norm — `@op(X, X, …)` where
  dst==src0, e.g. lines 308/344/380/457-465/932). Those ops **run fine on the CS-3
  device (1.13.2)** — proven by the baseline `test_device_2x2blk_kv` device run
  (which contains them). So a **local-sim operand-overlap crash is a 2.10 artifact,
  NOT a device bug — do not chase it.** compile-only locally is still fine for a build check.
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
- **CS-3 device launch = `run_device.sh` ONLY** (→ `launch_device.py` → SdkLauncher,
  which dispatches to a remote worker that has `cs_python`). **`cs_python` is NOT
  runnable on CS-3 from gala** — it's for the local simulator only; do not try it as
  a device path.
- **CS-3 gateway auth is intermittent** in >1 way: `Permission denied (publickey)`
  AND `Connection closed by UNKNOWN port 65535`. Both clear on **retry after ~70 s**
  (Le's manual workaround). Automate device runs with a retry loop that treats any
  transport error (rc 255) as retryable, `exceeded`/rc 124 as a real hang, and
  profiler/`SUCCESS` markers as done.
- **CS-3 coordinator discovery can transiently fail cluster-wide**: SdkLauncher logs
  `Could not find coordinator IP:port` / `Empty ingress service url. Falling back to
  default server: 10.27.24.65:443` and hangs (host never feeds the kernel; job shows
  "running" but starves). Seen as a real ~15 h outage 2026-07-06→07. **A config's own
  extra I/O streams can cause the SAME symptom** (job's `wsjob-coordinator-node-name`
  / `ingress_pes` stay empty). **Disambiguate by running the known-good baseline
  `test_device_2x2blk_kv` (no profiler)**: if baseline works but your config hangs →
  it's YOUR config (I/O streams / io_loc at full 512×512 scale), not the cluster.

## Important links

- InferCept (KV preserve/swap/discard cost policy): <https://arxiv.org/abs/2402.01869>
- Topic: [[kv-cache-policy-tradeoffs]], [[e2e-pdSeparate-device-validation]]
