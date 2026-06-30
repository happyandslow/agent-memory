# Qwen3-1.7B decode — dynamic KV load through chip ingress (design)

Date: 2026-06-30
Session: qwen-decode-kv-load
Repo: WaferEngine (`models/qwen3_1p7b-decode`)
Status: DESIGN — approved to move to implementation (per-file plan + ordered tasks below).
Plot: `2026-06-30-qwen3-dynamic-kv-load-ht_head-dataflow.png` (regen: `2026-06-30-qwen3-dynamic-kv-load-ht_head_plot.py`)

Related: the specdec dual-kernel note (`2026-06-30-specdec-dual-kernels-design.md`) calls
this the "dynamic-KV-loading decode kernel" needed for its **M2 warm-start** milestone.

## 1. Goal

Today the decode kernel's prefill KV is **baked into the compiled program** via
`set_symbol_all` (compile-time). Every request therefore needs a new artifact +
`runtime.load()` (~80s) — the batch model. The goal is to **load KV dynamically
through the chip ingress at runtime** (compile once, stream KV per request),
which is the streaming-inference primitive the serving path needs.

## 2. How KV is loaded today (baseline)

- Kernel buffers `XKCache_tile` / `XVCache_tile` are runtime-writable `export var`s
  (`decode.csl:421/424`); `process_kv()` already writes new K/V into them every
  decode step. **Only the initial prefill fill is baked.**
- Host generates per-PE-sharded KV tiles and pushes them in the per-row
  `set_symbol_all` loop (`launch.py:1461–1481`, `1573–1578`).
- `iter_num_bank` seeded from the `prefill_len_per_pe` param at `init_task`
  (`decode.csl:192`).
- The integration "external-KV" path (`integration/_staging_chain_*`) loads real
  prefill KV from an npz but **still via `set_symbol_all`** → still a recompile/
  reload per request. Not true ingress.
- Per-PE KV layout: K `[max_layers_per_block, bsz, kv_dim_per_pe, seq_len_per_pe]`,
  V mirror. **kv_dim sharded on X, seq sharded on Y (round-robin: pos p → Y-PE
  p%P, local col p//P), layer-banked.**

## 3. Investigation findings

### 3.1 Option C (re-bind a compiled symbol at runtime) — IMPOSSIBLE
The SDK has **no runtime symbol-write**. `set_symbol_all` is a `CodeRegion`
(layout/compile-time) method; its value is baked into the ELF at
`SdkLayout.compile()`. The runtime (`SdkRuntime`) can write device memory only via
`memcpy_h2d*` or `send()` port streams; the only symbol method is `read_symbol`
(READ-only, simulator-only). Confirmed at the binary level: the installed pybind
`.so` demangles to `cerebras::SdkLayout::CodeRegion::set_symbol_impl` (write,
compile-time) and only `cerebras::SdkRuntime::read_symbol` (read) on the runtime.
ELF-byte-patch + reload also fails the goal (still per-request `load()`).
→ See agent-memory note + auto-memory `reference_sdk_no_runtime_set_symbol`.

### 3.2 memcpy (Option A) — ruled out by user
`memcpy_h2d` into the symbols works (the `bench/layer_block` harness already does
exactly this) but needs `memcpy_required=True`; the full pipeline is built
`memcpy_required=False` with all 24 colors spent. User declined switching.

### 3.3 Option B (stream + kernel drain) — CHOSEN
Stream KV in over a host port; a kernel load-phase drains it into the cache banks
before the decode loop. The cache buffers are already runtime-writable; only the
*transport of the initial fill* changes.

### 3.4 Forward-path reuse analysis
KV must reach **every layer** (all PE blocks), unlike the token/X seed which lands
only on block 0. We checked whether the activation forward path is reusable:

| Forward-path piece | Reusable for KV? | Note |
|---|---|---|
| `inter_block_a/b` colors 19/20 + queues | Yes (time-multiplexed) | block→block conveyor |
| Strip K-pipe relay (`decode_strip.csl`) | Yes, structurally | already does own-vs-forward split = absorb-and-forward |
| Intra-block `intra_row_bcast` (broadcast) | **No** (topology reusable, semantics not) | KV is a **scatter** (distinct per PE); broadcast gives identical bytes |
| `main()` compute loop | No | need a non-compute **load phase** before the decode while-loop |
| All DSDs/buffers (`bsz*dim_per_pe`) | Resize | sized to the activation vector |

**Verdict:** reuse the long-haul conveyor (inter-block colors + strip relay,
time-multiplexed into a pre-decode load phase); build a new **intra-block 2D
scatter** (the one genuinely new routine; can reuse `intra_row_bcast`'s X-relay
*topology*, peel-per-column instead of copy) + the load-phase control. Beats a
fully separate KV path (which would burn scarce colors + re-derive the snake).

### 3.5 Ingress: reuse the demux corridor (pass-through HT) — CHOSEN
Decision: **pass through HT** for the simpler, less-error-prone design (vs a
dedicated TOP-edge port that bypasses HT but needs a new coordinate + lifetime-
pinned color + new connect into row_0).

Key correction from the discussion: the demux corridor is **HT-bound** —
`demux ─pre_embed_x(18)→ HT_head ─post_embed_x(23)→ row_0` (`launch.py:1891–1892`);
HT physically occupies `fab_x 3..PLACE_X-1` between the west edge and the decode
blocks, so west-side ingress must cross HT. You cannot reuse demux and skip HT.

### 3.6 HT_head relay design — reuse C1/C2, skip the vertical gather
The embedding uses two orthogonal motions (route paint `ht_head.csl:254–267`):
- **Horizontal, per-row:** C1 (id 18) WEST→EAST → drained (RAMP) at the row's
  diagonal column (`diag_col = py//2`); C2 (id 23) diag RAMP→EAST → row_0 PE of
  the same row index. **No N/S routes.**
- **Vertical, cross-row (the "diagonal structure"):** UP_A/B (21/22) + DOWN_A/B
  (8/9) gather `W_E[token]` N/S onto the diag pair + the table lookup.

**KV reuses the horizontal subset only.** In the load phase the diag PE just
drains a KV chunk on C1 and re-emits on C2 (exactly the step-0 X seed, looped),
skipping `embed_gather_dispatch` + the W_E lookup. Non-diag PEs need no logic
change — their painted C1/C2 routes already relay. Because C1/C2 are purely
horizontal/per-row, **all P_BLOCK_SIZE rows relay KV in parallel** (no cross-row
coupling), landing per-Y-row on row_0's same-index PE.

**Color choice = reuse C1 (18) + C2 (23). No new color, no new port.** Why safe:
(1) time-multiplexed (no embedding concurrent); (2) 18/23 are corridor-local (no
cross-region collision); (3) the routes already deliver per-row to row_0;
(4) C2's existing connect to row_0 is the only bridge into decode — reusing it
avoids new wiring. Not the gather colors (vertical = wrong direction; 8/9 alias
K-pipe ids). Not a fresh color (would need its own ports + a new connect into
row_0 = more work, zero benefit). Adjustments: diag-PE load loop; bump corridor
port `data_size` (currently `x_total_wavelets`, `launch.py:704/711/873/880/1228`)
to cover KV wavelets; phase gate.

See the plot (`...-ht_head-dataflow.png`): left = the reused C1→diag→C2 per-row
horizontal path; right = the UP/DOWN vertical W_E gather that KV skips.

## 4. Per-file change list (implementation)

- **`demux.csl`** — add a load-phase store-and-forward pass (reuse chain colors +
  recv→keep→forward-south→emit-east skeleton) at KV extents; loop chunks (less
  error-prone than resizing buffers). Runs before the X[0] single-shot.
- **`ht_head.csl`** — diag-PE load loop: drain C1 chunk → emit C2 chunk, repeat,
  gated to the load phase; skip `embed_gather_dispatch`/W_E lookup during load.
  Reuse colors 18/23. (No new color, no new port.)
- **`decode_strip.csl`** — parameterize relay extents (`strip_buf`, `kpipe_fwd_*`,
  `strip_fwd_extent`) so the own/forward chain carries KV slabs during load, then
  reverts to `bsz*dim_per_pe` for decode; add a load-phase `activate_*` entry.
- **`comm_pe.csl`** — (1) KV-extent variants of `inter_block_recv_x_sync` /
  `inter_block_send_z` (reuse colors 19/20, parity logic; resize DSD). (2) NEW
  **intra-block X-peel scatter**: each column keeps its `kv_dim_per_pe` band for
  its layers, forwards the rest east — reuse `intra_row_bcast` (id 6) route
  topology, peel-vs-copy drain. (seq/Y already pinned per-row by the conveyor.)
- **`decode.csl`** — load phase before `while (i < n_steps)`: recv KV off the
  conveyor → intra-block X-peel → write each PE slab into `XKCache_tile`/
  `XVCache_tile` at `set_layer`'s bank offsets. Gate `decode_struct()` off during
  load. Seed `iter_num_bank` on-chip from a streamed scalar `prefill_len` +
  `local_py` (`iter_num = prefill_len/P + (local_py < prefill_len%P ? 1 : 0)`);
  add an `iter_num_host_seeded`-style switch so `init_task` doesn't overwrite it.
  Add KV-extent ingress DSDs + a load→decode route repaint (reuse the
  `reconfig_allreduce_axis`/`set_route_*` pattern).
- **`route_calc.csl` / `route_util.csl`** — minimal if X-peel reuses id 6 + strip
  reuses K-pipe colors; precompute any load route set via `precompute_route_words`
  and add a load↔decode reconfig entry.
- **`mux.csl`** — no change.
- **`launch.py` (host)** — drop KV from `set_symbol_all` (keep zero-init export
  vars); add one KV input stream on the existing demux entry; reuse
  `device_reshard.kv_to_device` to order bytes for the demux→snake sequence; send
  KV before the X[0] seed; pass `prefill_len`, `iter_num_host_seeded`; bump
  corridor port `data_size`. No new ports/coordinates/lifetime-pinned colors.

## 5. Ordered tasks (de-risk first)

1. **Scatter spike** (sim, 2×2-block): implement the intra-block X-peel; verify a
   known KV pattern lands byte-exact in `XKCache_tile`/`XVCache_tile` vs the
   current `set_symbol_all` result. *(Only medium-risk new routine.)*
2. **KV-extent transport**: `decode_strip.csl` (N/S) + `comm_pe.csl` inter-block
   (E/W) carry KV slabs.
3. **Ingress corridor**: `demux.csl` + `ht_head.csl` load relays + host KV stream
   + port `data_size` bump.
4. **decode.csl load phase**: orchestration + bank writes + on-chip `iter_num`
   seeding + load→decode route repaint.
5. **Regression gate**: streamed-KV device result == baked-KV result (the
   `ext_kv` oracle in `host/oracle_fp16.py` already exists).

## 6. Risks / open items

- Intra-block X-peel is the one new routine (step 1 spike).
- Corridor port `data_size` must fit the (large) KV wavelet count; confirm no
  per-PE buffer blowup (`io_buffer_size` is separate, default 1024).
- Load latency: the full ~58 MB (device config) streams serially through demux→HT
  →snake — correct but slow; acceptable per the simplicity-over-speed decision.
- Whether the stream's port route can/should stay painted across phases (it's
  fixed for the run; load relay is time-multiplexed in kernel logic, not stream
  re-routing).
