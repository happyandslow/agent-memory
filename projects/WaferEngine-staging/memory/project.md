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
- Host-side serving/control helpers for a specific standalone kernel (KV-reuse store,
  retain/warm-start driver logic called by `launch.py`, forced-token serving helpers) live at
  the **model root beside `launch.py`**, one copy per kernel while kernel forms are still
  converging: e.g. `models/qwen3_1p7b-decode/kv_store.py` and
  `models/qwen3_1p7b-prefill/kv_store.py`. Do **not** put this class of serving-control code
  under `waferengine/engine/` yet (not wired/versioned against compiled kernel artifacts) or
  under `models/<kernel>/host/` (numerical oracle / precision tooling home reached via a path
  hack). Extract to shared engine code only after the kernel/compiled-binary form converges.

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
- **Real Qwen3 weights: true for the standalone kernels, NO LONGER TRUE for the pr14
  line** (corrected 2026-07-28). `qwen3_1p7b-decode` / `-prefill` and the `main`-line
  fused models are still mock/seeded — no HF loader, no Qwen3 gpu_reference oracle, no
  tokenizer (see [[e2e-pdSeparate-device-validation]]). But `qwen3_1p7b-e2e-pdSeparate`
  **at PR #14** loads real HF weights and bakes them into the ELF at compile time, and we
  have run it end to end on real WSE-3 with revision `70d244cc`
  ([[m2-s0-baseline-and-timer-provenance]]). ⇒ **always say which line a "mock weights"
  caveat applies to**; a performance number from the pr14 line is a real-weight number.
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

- **CS-3 ssh transport death can orphan wafer jobs.** If a `/cs3-runner`/`cs3-run.sh`
  device run exits `rc=255` with `Timeout, server cerebras not responding`, the guard's
  timeout-cancel path did not run; if a wafer `execute` job had already started, it may
  still be holding the wafer. When the gateway is reachable, run
  `csctl get jobs | grep <user>` and cancel any survivor before submitting more work.
  A true guard overrun ends with rc 124/cancel; ssh death ends with rc 255 and no cancel.
  (2026-07-21.)
- **Expect roughly half of a batch of device serve runs to die on cluster
  infrastructure.** Five identical `--mode reload` runs, back to back, same store:
  **two completed, three failed** — two with an EPCC ingress gRPC **502**
  (`Received http2 header with status: 502` from `10.27.24.65:443`, mid-run, preceded by
  `Error parsing metadata: … content-type: text/html`) and one with
  `ClusterJobInitError: … pod failure detected … [wsjob-…-worker-0]` during init. None
  were our code — the two that completed were bit-identical to each other and to the
  reference. These three self-cleaned (no orphan jobs). ⇒ **when a plan says "n = 5",
  budget attempts, not successes**, and say in the report which was achieved.
  (2026-07-28, M2-S0.)
- **Drive device runs with remote `nohup setsid` + log polling, not `cs3-run.sh`.** Its
  timeout path calls `cs3-jobs.sh cancel-mine`, which on this **shared** account would
  kill other tenants' jobs. `setsid` also survives ssh transport death (the rc=255 case
  above). The local ssh call returning **124 immediately after launching** the detached
  job is normal and does not mean the remote job died. To kill a run, cancel the specific
  wsjob id from its log. (2026-07-28.)
- **The Cerebras SDK singularity image cannot bind-mount anything under `/tmp`.**
  `cs_python` bind-mounts the working directory into the container at the *same absolute
  path*, and the container supplies its own `/tmp`, so the mount has no valid destination:
  `FATAL: container creation failed: … destination /tmp/… doesn't exist in container`,
  before any compile and with no CSL error. Put alternate checkouts (e.g. a
  `git worktree` of pre-change HEAD for an A/B inert gate) under `$HOME` instead — same
  command then works unchanged. This also rules out the agent scratchpad
  (`/tmp/claude-*/…`) as a run location; it is fine for logs and comparison scripts,
  which run on the host, but not for anything `cs_python` must `chdir` into. Sim-verified;
  a device run from an alternate path was not attempted. (2026-07-26.)

## Important links

- InferCept (KV preserve/swap/discard cost policy): <https://arxiv.org/abs/2402.01869>
- Topic: [[kv-cache-policy-tradeoffs]], [[e2e-pdSeparate-device-validation]],
  [[m2-s0-baseline-and-timer-provenance]]
