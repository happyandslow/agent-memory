# WaferLLM function-container M1 ABI checkpoint — 2026-08-14/15

**Project:** WaferEngine
**Author:** codex
**Status:** captured

## What happened / finding

- When starting Phase 1 Step 3 for the WaferLLM Decode Attention/FFN shared-slot
  design, M0 revalidated WaferLLM `fd1c2daae37cd68706c03fc8009887ecee9900f8`,
  design SHA-256 `edbac709d573ae4bbe55caa2377494ca62dee01a78143800662f9c3916debc38`,
  and the frozen production source/config hashes without modifying `Decode/`.
- M1 now has a versioned bounded-scalar CSL page ABI, JSON schema/manifest,
  deterministic ABI-artifact generator, declarative resident-symbol seed, and
  a one-slot contract. `manifests/abi_contract.json` is the sole hand-authored
  ABI source; it generates `common/page_abi.csl`,
  `common/resident_symbol_contract.csl`, and `manifests/abi_ids.json`
  byte-for-byte. Entry, command-sequence, profile, and buffer IDs remain
  unallocated for M2. `SLOT_ADDR`, DSD/DSR profiles, loader, dispatcher, and
  runtime remain deliberately unimplemented.
- The M1 resident data seed records 35 production-anchored f16 buffers/scalars,
  including `z_norm_tile`, RoPE `X_tmp_1..4`, and `dummy`, with a 2-byte minimum
  alignment requirement. This is not yet the full descriptor/pointer/DSR
  closure; M3 owns that placement decision.
- The deterministic generated-artifact check and cross-contract validator pass.
  The main validator invokes the generator's `--check`, re-hashes compile
  inputs/outputs, and scans both common declarations and compile-only CSL for
  forbidden fabric/queue/loader constructs. The SDK 2.10 compile-only fixture
  also passes and produced `out_0_0.elf` SHA-256
  `7c8b2b4cccf2ec95d3dfc55ace38f0800ccbc9ddb78d60f2998a3cd798012aa1`.
  The first real parser attempt exposed that CSL 2.10 rejects enum shorthand
  such as `.none`; imported enum members must be qualified, for example
  `page_abi.PageId.none`.
- User-authorized Claude Code review initially returned `PASS-WITH-FIXES`.
  It found JSON/CSL resident-symbol naming drift and missing automated
  compile-only forbidden-token coverage. Both were fixed; the targeted
  re-review returned `PASS` with no remaining issue.
- This is compile-only evidence. It does not validate transferred-page
  execution, a slot address, page entries, profiles, or receiver SRAM economics.
  M2 has not started.

## Implications / next actions

- [x] Complete the user-authorized Claude Code read-only M1 review, fix its
  findings, rerun deterministic validation and SDK 2.10 compile-only smoke, and
  stop for user review.
- [ ] Begin M2 only after the user accepts the reviewed M1 stage.

## Pointers

- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/STEP3_TRACKING.zh-CN.md`
- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step3-page-regions/`
- `/home/lexu/WaferLLM/MeshJit-Decode/FUNCTION_CONTAINER_DESIGN.md`
