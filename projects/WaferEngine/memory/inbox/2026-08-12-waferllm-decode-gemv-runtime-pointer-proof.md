# WaferLLM decode GEMV runtime-pointer proof — 2026-08-12

**Project:** WaferEngine
**Author:** codex
**Status:** drained
**Drained to:** `memory/topics/meshjit-code-relocation.md` (2026-08-14)

## What happened / finding

- In `/home/lexu/WaferLLM/MeshJIT-Decode-GEMV/`, an isolated 2-PE simulator
  proof loaded the exact 8-byte `cand_gemv_step` FMACH body from holder `.cand_gemv`
  at `0xa000` into receiver `.slot_gemv` at the same address, then executed it
  by a runtime function pointer for every component of a non-constant K=N=8
  GEMV. Holder resident and receiver relocated outputs were bit-exact (8/8 f16).
- The receiver ELF has no `cand_gemv_step` symbol; its 512-B slot is present at
  `0xa000`. The first two receiver-slot u32 words exactly match the holder ELF
  code bytes: `60091451 6d8003c0`. Inputs x/matrix/out are pinned identically at
  `0x8000`/`0x8100`/`0x8400`; receiver reserves DSR 1 mem kinds before calling.
- CSL SDK 2.10 rejects a runtime function pointer when `@map` is actually
  lowered: `only comptime-known variables can be used in comptime expressions`.
  A valid integration shape is therefore a resident traversal loop directly
  invoking the loaded `fn(f16) void` pointer; do not claim an unchanged resident
  `@map(gemv_static_step, ...)` offloaded the body.
- A loop-bearing dynamic driver prototype (80 B, source/slot both `0xa000`)
  stalled after its dynamic call in local sim. Address matching alone did not
  validate its broader closure. Treat loop-driver relocation as unverified here.
- The minimal correctness proof has gross body saving 8 B, slot cost 512 B,
  net −504 B. It is a feasibility result only, not an SRAM-saving or timing
  conclusion. No TSC timing or production decode substitution was performed.

## Implications / next actions

- [ ] On a warm CS-3 session, reproduce this exact Phase-1 harness once before
  claiming physical-WSE-3 correctness; do not use host wall as load latency.
- [ ] Restore an approved SDK-2.10-compatible resident Decode baseline first:
  its `comm_layout.csl:10` legacy `comptime_struct` signature fails before ELF
  generation (standalone MeshGEMV fails equivalently at `:16`). Only then make
  a small one-projection substitute using the resident direct-pointer traversal
  loop and inspect its final receiver ELF for accidental candidate retention.
- [ ] Keep the loop driver separate until its required global/DSD closure is
  reduced and its dynamic call is independently debugged.

## Pointers

- `/home/lexu/WaferLLM/MeshJIT-Decode-GEMV/README.md`
- `/home/lexu/WaferLLM/MeshJIT-Decode-GEMV/results/{sim_correctness.json,sim_symbols.json,map_runtime_pointer.compile.log}`
- `memory/topics/meshjit-code-relocation.md`
- ContextBase background: `2026-08-04 Result: MeshJIT physical multicast cost + real c512 use time`
