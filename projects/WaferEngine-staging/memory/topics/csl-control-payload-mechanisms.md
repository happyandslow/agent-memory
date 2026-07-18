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


## Architectural framing — no keyed routing; static orchestration primitives (2026-07-16)

The `qwen3_1p7b-prefill` KV-egress baton example sharpened the broader WSE fabric rule: there is no content/key-routed crossbar. A wavelet carries no destination field; routing is the compile-time painted route of its color, and runtime motion is limited to deterministic orchestration such as switch stepping, fixed chains, and control wavelets.

Worked example: the KV egress gather time-multiplexes a fixed WEST→EAST route. Exactly one PE emits (`pos_emit = RAMP→EAST`) while others forward (`pos_fwd = WEST→EAST`). The baton `kv_egress_turn2 = [SWITCH_ADV, SWITCH_ADV]` advances the current emitter to forwarding and the east neighbor to emitting; the tail uses `kv_egress_turn1 = [SWITCH_ADV]`. Correctness is count/order exact, with no key, ack, or runtime destination safety net; the spent tail baton must remain NOCE-filtered rather than delivered as data.

Design implication for KV reuse/tiering: any proposed many→one, route-by-request, retained-pool placement, idle-PE park/reload, or reverse prefill↔decode bridge must be expressed as a static topology plus deterministic stepper/rotate/chain primitive, or moved to the host. The ≤4 switch-position limit and reconfiguration cost are first-class design constraints for scaling gather fan-in.

Related primitives under the same lens: baton-gather (KV egress), rotate-and-match (HT_head vocab LUT), parity shift chains (inter-block shuttle), and chain all-reduce (comm_pe).

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

## Concrete example — Topic 7 (switches + control entrypoints), the canonical control wavelet

From `Cerebras/sdk-examples` `tutorials/topic-07-switches-entrypt/` (the doc-site tutorial pages
were removed in the site redesign; GitHub is now the canonical source). One control wavelet does
BOTH: advance a switch AND fire a control task.

- **Sender** (`send.csl`): a `.control = true` fabout DSD + `@mov32` of an encoded payload:
  `ctrl.encode_single_payload(opcode, suppress_ce_fwd, entrypoint, data16)`.
  - `encode_single_payload(SWITCH_ADV, true,  {},          0)` → advance switch, **no** control task (CE forwarding suppressed).
  - `encode_single_payload(SWITCH_ADV, false, recv_ctrl_id, 6)` → advance switch **and** fire the control task `recv_ctrl_id` with arg `6`.
- **Receiver** (`recv.csl`): `const recv_ctrl_id: control_task_id = @get_control_task_id(40);`
  `task recv_ctrl_task(data: u16) void { result[0] = @as(u32, data); }` + `@bind_control_task(recv_ctrl_task, recv_ctrl_id)`.
  Since no data task is on that color, must `@unblock(rx_iq)`/`@unblock(rx_color)` so the CE fires the control task.
- **Switch config** (`layout.csl`): `@set_color_config(x, y, color, .{ .routes=..., .switches = .{ .pos1={.tx=WEST}, .pos2={.tx=EAST}, .pos3={.tx=SOUTH}, .current_switch_pos=1, .ring_mode=true } })`. Each `SWITCH_ADV` advances the position.

## Task-type taxonomy + how many you can register (Async guide §3 / task-ids page)

| Task | ID constructor | Range | Fires on | Count |
|---|---|---|---|---|
| **Local** | `@get_local_task_id(n)` | 8–30 (WSE-3; 0–30 WSE-2; avoid 29,30 sys) | `@activate` / async callback — no fabric | — |
| **Data** | `@get_data_task_id(color|input_queue)` | *derived from* a color/queue | a **data wavelet** on that color/queue | **scarce** |
| **Control** | `@get_control_task_id(n)` | **0–63** (both archs) | a **control wavelet** carrying that id | **plentiful** |

- **Data tasks are the scarce ones** — each is welded to a color (WSE-2, ~24 colors minus memcpy 21/22/23) or an **input queue** (WSE-3: only **8 queues, IDs 0–7; queues 0 & 1 memcpy-reserved → ~6 usable per PE**). So on WSE-3 you get ~6 concurrent data tasks.
- **Control tasks: up to 64** (0–63), memcpy reserves 33–37 → ~59 usable; **not tied to a color/queue**, so cheap and routeless. WSE-3 can give each queue its own control-task table (`ctrl_table_id`). Caveat: the `encode_single_payload` **entrypoint field is ~5-bit** (switch+task combined); a pure sentinel via `encode_control_task_payload(id)` reaches the full 0–63 (examples use 40/42/43).

## Routing change is the SWITCH, not the control task (important correction)

A control wavelet has **two independent consequences**: (1) **router** — advance/reset a switch (changes routing); (2) **CE** — activate a control task. These are separate, toggled by different payload fields.
- **Changing a color's routing at runtime = the switch mechanism**, NOT a control task. Needs `.switches` pre-declared in `@set_color_config`; a `SWITCH_ADV` control wavelet then advances the position. It happens **at the router as the wavelet passes through the PE** — no `RAMP`, no control task needed (`suppress=true`). Even a pure transit `rx=WEST,tx=EAST` PE re-routes for **subsequent** wavelets (the control wavelet itself still exits on the *current* position).
- **Limited runtime control**: switches only cycle among pre-declared positions 0–3; you cannot synthesize an arbitrary new route at runtime.
- A **data task cannot** change routing (needs RAMP delivery, which a transit color lacks); a **control task also isn't the mechanism** (and at a no-RAMP transit PE no control task fires at all — only the switch acts).

## "Non-routable" — precise meaning (corrects earlier loose wording)

- The control **wavelet IS routed** — it "uses the same color infrastructure" and follows the color's `rx`/`tx` route exactly like a data wavelet.
- What is **non-routable is the control task ID** — it is not a color, has no route of its own; it's a **dispatch selector** for which CE handler runs once the wavelet is delivered. (Sentinel tutorial: "control task IDs are not routable colors… does not specify a route.")

## How much can a control wavelet carry? — 16 bits

A wavelet is 32 bits. In a **control** wavelet those bits encode the command (opcode + suppress bit + entrypoint) leaving a **16-bit data field** handed to the control task as its arg (`task f(data: i16)`). So **≤16 bits of user data per control wavelet**. For more: multiple control wavelets, or **data** wavelets (full 32 bits each) with a header peel. (WSE-3 `dense_mode` packs 2×16-bit per *data* wavelet, not control.)

## Backend CE-dispatch mechanism (the control bit is the first discriminator)

- A wavelet = **32-bit payload + a hardware control flag** (`.control = true` on the sender's fabout DSD). Routed by **color**, identical for data and control.
- On arrival where the route sends to `RAMP`, on WSE-3 the wavelet enters the **input queue** bound to that color (queue depths 2–6 wavelets). The **first-level discriminator is the control flag**:
  - **flag=0 (data)** → queued → activates the **data task** bound to that queue; single-wavelet = payload is the task arg, multi-wavelet = drained by a `fabin_dsd` via `@mov*` (async, a microthread pulls N off the queue). ("wavelet → queue → drained by task" is right for data.)
  - **flag=1 (control)** → **not** enqueued as data ("control wavelets modify router behavior rather than carrying data to the CE"); the router acts on any switch opcode, and if CE-forwarded the CE dispatches via the **control-task table** to the id-named control task, handing it the 16-bit field.
- **Same color can carry both** — data wavelets fire the data task (on the queue), the control wavelet fires the control task (on its id); topic-05 `pe_program.csl` binds BOTH on one color as proof. Conditions: route delivers to RAMP at that PE, `suppress=false`, the id is bound (and on WSE-3 in the queue's ctrl table), channel unblocked. NB: you bind the control task to an **ID**, not "to the color."
- **Sourcing caveat:** the public docs describe this at the *programming-model* level (the `.control` flag, data-task-by-queue, control-task-by-id-table, "modify router behavior not carried to CE"). They do NOT publish a gate-level cycle sequence — "control bit checked first" is the documented *behavioral contract*, not a published micro-arch pipeline. Exact silicon ordering = a question for Cerebras.

## SDK doc-site URL mapping (post-redesign, sdk.cerebras.ai, verified 2026-07-12)

The redesign **removed the standalone Topic 5/6/7 tutorial pages**; several earlier `sdk.cerebras.net/...` URLs 404. Current homes:
- Tasks (data/control/local, ids, activation): `https://sdk.cerebras.ai/csl/language/task-ids`
- Colors/routing/switches (folded in) + color-swap: `https://sdk.cerebras.ai/csl/language/advanced-features`; base routing tutorial `https://sdk.cerebras.ai/csl/tutorials/gemv-06-routes-1`
- Fabric DSDs / queues / FIFOs: `https://sdk.cerebras.ai/csl/language/dsds`
- Language index: `https://sdk.cerebras.ai/csl/language_index`; full machine index: `https://sdk.cerebras.ai/llms.txt`
- **Control wavelets / switches / sentinels tutorials → GitHub (canonical, stable):** `https://github.com/Cerebras/sdk-examples/tree/master/tutorials` (`topic-05-sentinels`, `topic-06-switches`, `topic-07-switches-entrypt`).

## Last updated

2026-07-18 (added no-keyed-routing/static-orchestration framing from KV egress baton); 2026-07-12 (enriched: concrete topic-07 example, task-type limits, switch-vs-control-task routing
correction, "non-routable" precision, 16-bit capacity, CE-dispatch/control-bit mechanism, post-redesign
SDK URL mapping). Original capture same day: M0/S4 design input from csl-knowledge KB v2.10.
