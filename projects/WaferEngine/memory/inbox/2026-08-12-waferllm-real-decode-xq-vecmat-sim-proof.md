# WaferLLM real Decode xq `vecmat_computation` dynamic-load simulator proof

Date: 2026-08-12
Project: WaferEngine
Status: drained

An isolated experiment at
`/home/lexu/WaferLLM/MeshJit-Decode/mirror-xq-phase/` now substitutes the
SDK-2.10 Decode mirror's real xq vecmat boundary without changing production
`Decode/WSE-3/`.

Durable results:

- Valid config: P=4, group_num=2, bsz=2, dim_p_pe=8 (16 compute PEs).
- The resident entry executes the mirror's real `rmsnorm_x()` followed by
  `xq_matvec_mult()` and the unchanged whole `vecmat_computation()`.
- The candidate is linked at 0xa000, 264 B / 66 u32, SHA-256
  `0ff58e36fbcc36a8f41b859d4a72fdc8a177b42598956cbca181ba2003684aba`.
  This is 36 B larger than the prior bsz=1 228-B body because the source
  `@range(bsz)` batch traversal is compile-time expanded.
- Compute PE (3,0) also serves as holder to keep the simulator at 16 PEs. It
  locally admits its own slot and sends one fixed-count stream through a
  Hamiltonian snake; router taps populate the other 15 slots.
- Every receiver has a 512-B slot at 0xa000 and an identical 38-B initial
  `.vecmat_abi` at 0x8800. Dynamic receiver ELFs have no `.cand_vecmat`,
  `vecmat_computation`, or `gemv_static_step` symbol. Final relocations are
  empty in all audited ELFs.
- Each receiver slot prefix exactly matches all 66 resident ELF words and its
  unused tail remains zero. After slot execution, all 768 QKV f16 elements are
  bit-exact against resident under identical nontrivial signed X/W/Q inputs.
- Code loading uses color 1 and IQ/OQ 2; Decode collectives use colors 5-9 and
  IQ/OQ 3-7. The color-audit tool refused the mirror because it lacks the
  expected `launch.py`, so the result records a source-derived resource table,
  not a tool safety verdict.

Debugging controls:

- P=2 is not a valid baseline for this two-phase Decode all-reduce. With
  group_num=2 the group size is one but phase 1 still performs an unconditional
  receive; group_num=1 similarly degenerates phase 2. The observed resident
  stall was therefore independent of MeshJIT.
- The first P=4 snake route omitted NORTH inputs at row starts and stalled
  after the first turn. Adding the two generic row-start cases fixed the exact
  symptom; the corrected artifact passes.

No SRAM benefit is claimed. The single candidate saves 264 B gross, but the
current receiver adds a 512-B slot and 320 B of `.text`; the uniform proof also
exports a 512-B payload buffer on every PE. Multi-candidate shared-slot work is
allowed only after reproducing this correctness gate on CS-3.

Primary artifacts:

- `MeshJit-Decode/mirror-xq-phase/README.md`
- `results/payload_test_p4_b2.json`
- `results/elf_audit_test_p4_b2.json`
- `results/sim_resident_test_p4_b2.json`
- `results/sim_dynamic_test_p4_b2.json`
- `results/validation_test_p4_b2.json`
