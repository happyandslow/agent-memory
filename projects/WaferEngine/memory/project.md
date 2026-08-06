# WaferEngine Project Memory

## Identity

- Project slug: `WaferEngine`
- Human name: `WaferEngine`
- Owner: Le Xu
- Area: `10-work/WaferEngine`
- Confidentiality/access boundary: 

## Source of truth

- Code repo: git@github.com:happyandslow/WaferEngine.git
- Remote server path(s): gala2:/home/lexu/WaferEngine
- Local checkout path(s): 
- Obsidian path: `/Users/lexu/Library/CloudStorage/GoogleDrive-lxu5398@gmail.com/My Drive/Obsidian-note-vault/note-vault/10-work/WaferEngine`
- Memory repo path, Mac: `/Users/lexu/Projects/agent-memory/projects/WaferEngine`
- Memory repo path, remote/gala2: clone `agent-memory` as `/home/lexu/agent-memory`, so project memory is `/home/lexu/agent-memory/projects/WaferEngine`
- Portable routing rule: in the work repo, resolve `$AGENT_MEMORY_ROOT`; otherwise use sibling `../agent-memory`; otherwise use the Mac fallback `/Users/lexu/Projects/agent-memory`.

## Machines and agents

| Host | Role | Paths | Notes |
| --- | --- | --- | --- |
| gala2 | primary development | work repo `/home/lexu/WaferEngine`; memory repo `/home/lexu/agent-memory` | Sibling layout makes `../agent-memory/projects/WaferEngine` valid from the work repo. |
| MacBook | Obsidian/Hermes/local view | `/Users/lexu/Projects/agent-memory/projects/WaferEngine` | Obsidian view under `10-work/WaferEngine`. |
| Mac mini | backup |  | Clone/pull memory repo only if needed. |

## Commands

### Build/test/check

```bash
# fill in
```

### Status update

```bash
# fill in
```

## Conventions

- 

## Known pitfalls

- **`ssh CS-3` → "Connection closed by UNKNOWN port 65535" is EIDF gateway connection
  exhaustion, not a broken local socket.** The `CS-3` alias has no ControlMaster (only
  `RemoteCommand` + `ProxyJump`), so every `ssh CS-3` opens a fresh gateway connection; the
  automation alias `CS-3-cmd` *does* have a ControlMaster (the warm path), which is why automation
  keeps working while interactive login fails. Leftover long-lived interactive `ssh CS-3` sessions
  each hold a gateway slot; with the automation tunnel too, new connects get refused (leading
  diagnosis: gateway cap / per-IP rate-limit — `MaxStartups`/fail2ban). *[unverified: the
  65535-refusal → gateway-cap causation is diagnosis; retry-after-cleanup not confirmed.]* To
  handle: check local ControlMaster state with `ps`/`ss` only (never `ssh` to probe); kill leftover
  interactive `ssh CS-3` PIDs (the ProxyJump pair) but **preserve `CS-3-cmd`** — do not
  `rm ~/.ssh/cm/*` (kills the warm path, forces a fresh OTP login). Do NOT loop-retry the failing
  `ssh CS-3` (fail2ban lockout risk); wait a few minutes, diagnose with `ssh -v CS-3` (first ~20
  lines). Distinct from the WaferEngine-staging run-transport death case
  (`2026-07-21-cs3-ssh-death-orphans-wafer-job`). Procedural CS-3/EPCC-general → **promotion
  candidate for the `cs3-run`/`cs3-runner` connection-troubleshooting section.** (Drained from
  `memory/inbox/2026-08-05-ssh-cs3-connection-closed-port-65535-gateway-exhaustion.md`, 2026-08-05.)

## Important links

- 
