# WaferLLM Decode vecmat dedicated-holder CS-3 proof — 2026-08-13

**Project:** WaferEngine
**Author:** codex
**Status:** captured

## What happened / finding

- When validating whether a function-storage PE can supply the full real
  Decode `vecmat_computation` body to otherwise uniform compute PEs, the
  isolated `MeshJit-Decode/mirror-xq-phase` P=4, bsz=2 gate passed on a
  physical CS-3.
- The dynamic layout used 16 compute receivers, holder `(4,0)`, and three inert
  rectangle fillers `(4,1..3)`. The host staged the payload only to the holder.
- The holder multicast the 264-B / 66-u32 body into address-matched `0xa000`
  slots. Readback proved all 16 prefixes matched SHA-256
  `0ff58e36fbcc36a8f41b859d4a72fdc8a177b42598956cbca181ba2003684aba`;
  every remaining word in each 512-B slot was zero.
- Resident and dynamic artifacts used identical deterministic signed X/W/Q
  inputs. All 768 returned f16 QKV elements were bit-exact; Q was nonzero and
  the xq-only gate left K/V zero.
- Audit of the actual cloud-linked ELFs, not only the local simulator ELFs,
  passed: resident candidate at `0xa000`, receiver `.cand_vecmat` and candidate
  symbols absent, resident/receiver 38-B ABI initial images identical, no final
  relocations, and holder/filler closure separation intact.
- This is a correctness result, not a timing or SRAM-saving result. The current
  receiver has a 512-B slot and a 320-B `.text` increase over resident; shared
  use by additional mutually-exclusive candidates is still needed for a net
  SRAM argument.

## Implications / next actions

- [ ] Review whether to reduce the one-map admission floor or add a second real
  mutually-exclusive candidate to demonstrate shared-slot SRAM benefit.
- [ ] Only after the boundary is chosen, measure phase-level load/use with the
  on-device TSC protocol.

## Pointers

- `/home/lexu/WaferLLM/MeshJit-Decode/mirror-xq-phase/README.md`
- `results/device/test_p4_b2/validation.json`
- `results/device/test_p4_b2/elf_audit.json`
- `results/device/test_p4_b2/run_device.log`
- Previous static gate:
  `memory/inbox/2026-08-12-waferllm-dedicated-holder-static-audit.md`
