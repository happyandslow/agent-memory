---
summary: E9 force-decode segment timing — why it lives in ht_tail and not the block PE, the 4-way burst-width contract, and the two silent-failure bugs found in review.
tags: [waferengine-staging, m2, e9, tsc, instrumentation, cerebras-sdk]
---

# E9 · force-decode segment TSC — design, and the two ways it silently failed

Built 2026-07-31 on `/home/lexu/we-m2bench` (branch `lexu/staging/m2-benchmark`, base `dd0d950`),
uncommitted. Files: `src/decode/ht_tail.csl`, `src/decode/mux.csl`, `launch_decode.py`.

## Why the measurement is NOT on the PE that runs the forced steps

The obvious home is `decode.csl`, where the forced loop actually runs. That was built first and
**thrown away**, for a reason worth keeping:

- A **block PE has no free color or output queue.** A TSC burst there needs new fabric, which would
  race the main data path — i.e. perturb the thing being measured.
- The escape hatch that made a block PE look viable was leaving the pair in `export var`s and calling
  `runtime.read_symbol()` after the round. **That does not work on hardware** — `read_symbol` is
  simulator-only (see [[read-symbol-is-simulator-only]]). On simfab it would have produced numbers;
  on the wafer, nothing.

**The fix was to move the measurement, not the transport.** `ht_tail`'s `is_tsc_pe` already has
(a) an armed TSC counter, (b) a per-round burst that rides `logits_south_oq` and is already drained
end-to-end, and (c) **this round's `F`**, which it receives in the X' budget header
(`forced_decode_len = nstep_hdr_buf[1]`). Nothing new had to be created.

**Span:** top of `tail_step == 0` → top of `tail_step == forced_decode_len`. Both ends sampled at the
same point of the loop body, so the pipeline offset between the block PE and HT_tail cancels and the
interval is a whole number of F steps.

## The burst width is a 4-way contract

Widening the burst 8 → 16 u32 requires **four** coordinated edits. Miss one and surplus wavelets park
in the fabric, desyncing the next round:

1. `ht_tail.csl` — `tail_tsc_out_dsd` extent (the producer)
2. `mux.csl` — `tsc_burst` / `tsc_recv_dsd` / `tsc_send_dsd` (**the relay hardcodes the width**; this
   is the one that is easy to miss, and `mux.csl` is a different file from where you are working)
3. `launch_decode.py` — `runtime.receive(logits_stream, ..., N)`
4. `launch_decode.py` — the egress **port budget** `south_total_with_tsc = south_total_wavelets + N`

`demux.csl` has no TSC relay. `kv_ingress_adaptor.csl` has its **own separate** 8-u32 burst on the east
edge (M2-S1b) — a different path, deliberately untouched.

Slot map after widening: `0..2` steady start, `4..6` steady end, `8..10` fd start, `12..14` fd end,
`15` = F as the device saw it; `3`/`11` pad. Even width is an SDK requirement for an output port.

## Two silent failures found in review — both "runs fine, data missing/wrong"

Neither would hang, error, or slow anything down. You find them by reading `timing.json` after the run.

**1. `F == N` never reported the span.** The normal burst emit sits at the *bottom* of iteration
`n_steps-1`; the fd toc fires at the *top* of iteration `F`. At `F == N` the toc is one iteration too
late, and the terminator's emit was guarded by `tail_step < n_steps`, so nothing re-emitted. Result:
`fd_tsc_f == 0`, host reports `None`.
⇒ Fixed with a per-round **`tsc_emitted` flag**: the normal site defers when `forced_decode_len ==
n_steps`, and the terminator emits instead. The flag replaced `tail_step < n_steps`, which could only
express "not the terminator yet" and not "the burst is still pending".
⚠️ **`F == N` is not an exotic setting — it is the one you drift toward**, because E9 exists to kill the
uncontrollable free tail and `N == F` kills it completely.

**2. A short LAST round discarded the whole run.** The fd fields were first computed inside
`if counted_tokens >= 1:` — a gate belonging to the *steady-state* metric, which needs the last round
to have generated more than `warmup_cycles`. One short final round ⇒ `"tsc": null` ⇒ **every round's**
forced measurement lost, including rounds that measured perfectly.
⇒ Fixed by computing `per_round_fd` **outside** that gate and giving it its own top-level verdict key
`"forced_segment"`. The fd measurement depends on neither warmup nor the last round; it self-validates
via slot 15.

**Generalisable lesson:** when adding a field to an existing telemetry block, check what the *enclosing*
guard is actually gating. Inheriting an unrelated precondition is invisible until the precondition fails.

## Verified

Decode-only compile on CS-3, **`rc=0` in 4 min 44 s** (`--mode compile --build-phase decode`, scratch
store `e9_compile_store`, S30's `serving_cache` untouched); re-run `rc=0` after the host-side fixes.
That settles: both casts compile, plain `fn` (not `noinline`) is fine for the packer, mux `in_q` accepts
16 wavelets, and HT_tail PE data memory still fits.

**Not verified:** anything about hardware behaviour. Compiling is not running. Per project rule, the
first thing on device is a **payload-proportionality check — vary F and confirm the span moves
proportionally** — not a division. `F=1` is the built-in control; the `F == N` path has never executed.
