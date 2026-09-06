# Running production decode function bodies under a simulator overlay: four consumed candidates — 2026-08-31

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured

## Situation this applies to

You want to execute *unmodified production kernel function bodies* in simfab and
read device state back, without touching the production sources, flags or ABI —
a verification overlay rather than a test kernel. Everything compiles, host unit
tests are green, and the run still fails at a different point on each attempt.
Four immutable candidates (FIX3–FIX8) were consumed on plumbing alone before a
single numerical comparison happened. Each failure below has a distinct symptom;
knowing them collapses that chain.

## What happened / finding

Four independent plumbing blockers, in the order they surfaced:

1. **`read_symbol` needs a core dump, not just the simulator.** Beyond the known
   "simulator only" restriction, the run must be launched with
   `get_platform(cmaddr, SimfabConfig(dump_core=True), SdkTarget.WSE3)`.
   *Symptom:* compile OK, `load()/run()/stop()` all return normally, then the
   **first** `read_symbol` fails — "no core dump was produced". Confirmed by the
   installed SDK 2.10 tutorial `examples/tutorials/sdklayout-01-introduction/run.py`,
   which is the exact working sequence: `dump_core=True` platform →
   `SdkRuntime(..., memcpy_required=False)` → load/run/**stop** → `read_symbol(x, y, sym, dtype=...)`.
   Reads happen **after** `stop()`, and the coordinates are SdkLayout-grid
   coordinates.

2. **The memcpy route is closed for this model.** Trying `memcpy_required=True`
   first fails with "No memcpy binaries were found" → `RuntimeError: SdkRuntime
   does not support programs without memcpy`; adding `--memcpy --channels=1` to
   the compile then fails because this model's `cslc-driver` wrapper rejects
   those flags outright. Don't spend a candidate rediscovering this — go
   straight to `memcpy_required=False` + core-dump `read_symbol`.

3. **Region-major vs lane-major tile layout.** `QKV_tile` is laid out
   **region-major** — Q region `[0, bsz*attn_per_pe)`, then all K, then all V —
   not as per-lane `[Q_b|K_b|V_b]` blocks. Installing or decoding it lane-major
   scrambles every downstream stage. Cross-check any such assumption against the
   kernel's own offset arithmetic (`apply_rope_k`'s `qkv_offset = bsz*attn_per_pe`,
   `process_kv`'s K read), not against intuition.

4. **Bypassing `kv_ingress()` silently breaks every collective.** IQ7/OQ7 boot
   bound to the KV-ingress colors, and the *sole* rebind to the collectives'
   broadcast color is the OQ7 empty-queue handler `kv_ingress_oq_empty`, reached
   only via `kv_ingress_flush_then_resume()`. An overlay that jumps straight to
   its own driver leaves queue 7 on the ingress color: the reduce-toward-root
   leg still makes progress (those queues are boot-bound) but the broadcast-back
   starves every PE. *Symptom:* the stage completes on **no** PE — all 64
   completion markers zero — while partial reduction progress is confined to the
   root row, and collective-free stages (e.g. rope) pass fine. The repair is to
   call the existing production `kv_ingress_flush_then_resume()` and let the
   production handler do the rebind, adding no queue programming of its own.

## Implications / next actions

- [ ] For any future overlay: pin the four above before freezing a candidate —
  each one costs a full immutable freeze + rehash + run cycle otherwise.
- [ ] **Promotion candidate (procedural, not project-specific):** items 1 and 2
  are SDK-level and would recur on any SdkLayout verification harness; they sit
  next to the existing `read-symbol-is-simulator-only` note, which covers the
  simulator restriction but *not* the `dump_core=True` prerequisite or the
  read-after-stop ordering. Propose extending that topic (maintain pass) or a
  small skill; do not install from here.

## Pointers

- `WaferEngine-staging/models/qwen3_1p7b-decode/tests/s0_layout_adapter.py`,
  `s0_symbol_readback.py`, `s0_overlay.py`, `run_s0_verification.py`
- `WaferEngine-staging/.s0-artifacts/m1b-s0-part1-20260831-ae-fix{3,4,5,6,8}`
- SDK 2.10 `examples/tutorials/sdklayout-01-introduction/run.py`
- Related: [[read-symbol-is-simulator-only]], [[csl-control-payload-mechanisms]],
  [[a-queue-that-looks-idle-can-hold-a-parked-async-op]]
