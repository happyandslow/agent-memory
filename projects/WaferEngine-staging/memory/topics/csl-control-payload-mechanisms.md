---
summary: CSL (WSE-3, SDK v2.10) supports control payloads that instruct PE actions — control wavelets (opcode + control-task entrypoint + 16-bit arg), switch-advance/reset/teardown, data-task-by-color, header-peel, and async .on_control termination. Input to the M0/S4 metadata-carrying on-chip KV relay.
tags: [waferengine-staging, csl, wse-3, control-wavelet, fabric, switch, s4, kv-relay, metadata]
---

# CSL Control Payloads — mechanisms that let a transmitted payload instruct a PE

Captured 2026-07-12 (design input for **M0/S4**, the metadata-carrying on-chip KV relay).
Source: `csl-knowledge` MCP KB, **v2.10** — `CSL_Routing_Colors_Switches_Guide.md` (§4 switches,
§5 control wavelets, §6 sentinels, §7 filters, §11 API, §12 pitfalls); library
`source-code/csl_libraries/control.csl` (opcodes + payload bit layout);
`CSL_SdkLayout_DirectLink_Pattern_Guide.md` (SWITCH_ADV demux); `CSL_DSD_Complete_Guide.md`
§10.7 (`.on_control`); `CSL_Async_Programming_Guide.md` (task classes); WSE-diff §10/§13.
Related: [[e2e-kernel-dataflow-and-topology]], [[pr14-real-serving-port-contract]].

## Bottom line

**Yes — CSL has a first-class control payload.** Two complementary mechanisms let a *transmitted
payload instruct a PE action* rather than just landing in memory as data:

1. **Control wavelet** — a 32-bit wavelet flagged `.control = true` on the sending `fabout_dsd`.
   The router interprets it as a *command*. Its payload (built via the `<control>` library) packs:
   an **opcode**, a **control-task entrypoint** (which control task to fire on the receiver), and a
   **16-bit `data` argument** passed to that task. So one control wavelet can both reconfigure the
   fabric AND fire a typed handler with a small argument.
2. **Data task by color (implicit)** — a data wavelet arriving on a color activates the data task
   bound to that color (`@bind_data_task`); the task reads the 32-bit payload (`task f(data:u32)`)
   and branches on it. Choice of *color* already selects the action; peeling a **leading header
   wavelet** (length/flags) then treating the rest as data is idiomatic (this is exactly the
   existing KV meta-tile peel, `KV_META_LEN=2`).

## The mechanisms (with API)

- **Control wavelet payload layout** (`control.csl`): bits 0–15 = 16-bit `data` arg; bits 16–20 =
  entrypoint (`control_task_id`, value 31 = "null / no CE task"); bit ~22+ = opcode + CE-filter.
  Encoders: `ctrl.encode_single_payload(opcode, ce_ignore, entrypoint, data)`,
  `ctrl.encode_control_task_payload(task_id)`, `ctrl.encode_payload(...)`. Send by `@mov32`-ing the
  encoded value into a `fabout_dsd` with `.control = true`.
- **Switch reconfiguration by wavelet** — opcodes `NOP=0`, **`SWITCH_ADV=1`** (advance router
  position), **`SWITCH_RST=2`**, **`TEARDOWN=3`** (reset to pos0). A color is given a switch in
  `@set_color_config(.{ .routes, .switches, .current_switch_pos, .ring_mode })` with up to 4
  positions. This is the canonical "payload changes routing mid-stream" primitive — **the
  io_pipeline demux already uses `SWITCH_ADV`** so PE0 advances RAMP→forward.
- **Control task** — receiver binds a handler with `@bind_control_task` (control_task_id 0–63; the
  wavelet-encodable entrypoint subset is 0–30). WSE-3 adds per-input-queue control-task tables via
  `@initialize_queue(..., .ctrl_table_id=N)` + `@set_control_task_table()` (avoids id collision with
  local/data tasks), and `@bind_rotating_tasks` (fire a control task every Nth data activation).
- **Async `.on_control` hook** (`CSL_DSD_Complete_Guide.md` §10.7) — an async `@mov16/@mov32` can
  react to an inbound control wavelet mid-transfer: `.on_control = .{ .terminate=true }` (end the op
  → **length-agnostic receive**, terminated by a control wavelet), `.{ .activate=task }`, or
  `.{ .unblock=task }`.

## Limits / gotchas

- Control-wavelet **`data` arg is only 16 bits** → a `retain` bool + a length ≤ 65535 fits; a wider
  length needs a **data-wavelet header** peel instead.
- Entrypoint field is **5 bits** (0–30 usable; 31 = null) → wavelet-reachable control-task
  entrypoints are a scarce, small-numbered resource.
- **Do not mix data and control on one DSD** (corruption) — use a separate `.control=true` DSD.
- **Switch-advance ordering hazard** — a switch advances *when the control wavelet passes*, so
  control/data interleave order on the wire decides which neighbor each data wavelet hits; a wrong
  `current_switch_pos` sends the first data the wrong way.
- WSE-3: `fabric_color` deprecated on `fabin/fabout` (color from `@initialize_queue`); control DSDs
  follow the same `if (@is_arch("wse3"))` portable pattern.
- **No content/key-based routing** in the fabric — routing is by *color* or by wavelet *index*
  filter (§7), never by payload key. "Route KV by request-key" stays a data-task/addressing policy,
  not a fabric feature (consistent with `cerebras-kernel-comm-patterns`).

## Design takeaway for M0/S4 (metadata-carrying on-chip relay)

S4 wants to carry a per-round meta header — a **length** + a **`retain` flag** — on-chip *alongside*
KV and have PEs act on it. All supported:

- **Length** → a **leading data-wavelet header** peel (full 32-bit, no 16-bit cap), or an async
  receive terminated by `.on_control = .terminate` (length-agnostic).
- **`retain` flag / per-round action** → fold into the same data header, OR send as a **control
  wavelet with a control-task entrypoint** so a dedicated `retain`/`discard` handler fires on the
  relaying/decode PE — a *typed control event* separate from the KV data stream (16-bit arg is ample
  for a flag + small count).

So the S4 "embed metadata + link it to the transferred KV data" idea is **fabric-supported**, not a
new capability — it is the existing meta-tile peel (data path) optionally upgraded to a control-task
event (control path). This does **not** by itself resolve the S4 sizing question (whether the pr14
injector input edge/color is reconnectable on-chip) — that still needs the deferred device dig.

## Last updated

2026-07-12 (M0/S4 design input; captured from csl-knowledge KB v2.10).
