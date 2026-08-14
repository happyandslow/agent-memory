# WaferLLM SDK-2.10 `vecmat_computation` dynamic-load simulator proof

Date: 2026-08-12

**Status:** drained
**Drained to:** `memory/topics/meshjit-code-relocation.md` (2026-08-14)

`WaferLLM` main at `fd1c2da` (SDK-2.10 migration) now has an isolated proof
at `/home/lexu/WaferLLM/MeshJIT-Decode-Vecmat/` for the current decode
`vecmat_computation` boundary.

Measured simulator facts (`K=N=8`, `B=1`):

- Candidate `cand_vecmat_computation` is 228 B / 57 u32 at holder `0xa000`.
- Receiver slot is address-matched at `0xa000`, fixed at 128 u32 / 512 B;
  exactly 57 words transfer and the tail is zero.
- Candidate includes the real WaferLLM DSD length/base setup, DSR-1 loads, and
  `@map` of the one-FMACH callback. The final holder ELF has no external
  `gemv_static_step` symbol; receiver ELF has neither candidate nor callback.
- Nontrivial signed FP16 8x8 GEMV output was bit-exact between holder resident
  and receiver dynamic execution: bits
  `[46897,48922,17552,43348,11572,15972,50195,16819]`.
- Holder/receiver `.vecmat_abi` data sections must be byte-identical: 46 B at
  `0x8800`. The required closure includes the mutable left/right/out DSDs,
  pointer state, `Kt`/`Nt`, DSR-1 kinds, and x/matrix/out locations.
- Receiver linkage initially pruned opaque-code DSD state, causing simulator
  `Invalid address 0x6000 for SRC1`. An explicitly no-FMACH liveness anchor
  plus reset before the slot call retained the ABI. Treat this as a required
  linker/ABI retention step, not a hardware issue.
- `@map` rejects runtime callback pointers (comptime-only). Offload the whole
  driver or retain a resident traversal; do not claim dynamic replacement of
  the callback.

No decode production code was changed, no timing was measured, and no CS-3
claim is made. Next gate is one-projection decode-path substitution with the
same no-resident-body/ABI/bit-exact audit, then TSC timing and device replay.

ContextBase log: https://context.ed-aisys.com/doc/2026-08-12-waferllm-vecmat-dynamic-load-simulator-proof-sdk-210-4Kg85z5zir
