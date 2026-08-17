# WaferLLM function container M5R receiver ABI — 2026-08-17

**Project:** WaferEngine
**Author:** codex
**Status:** captured

## What happened / finding

- Situation: linking Attention and FFN pages separately made the supposedly
  common `.m5_pinned_data` and binder-state sections differ in size and hash.
  Requiring whole-section byte identity was an invalid receiver-ABI test: each
  page compilation legitimately retains only the receiver objects it refers to.
- M5R-0 replaces that test with a per-symbol receiver-union contract.  The
  receiver owns the union, while each page must eventually prove
  `page-linked symbol address == manifest address == receiver ELF address` only
  for the objects it consumes.  The frozen union has 33 unique fixed objects:
  persistent tensors/weights/KV/scratch, `local_sum`, `local_max`, `alpha`, and
  `page_control`.  It contains no retention function, alias table, shadow
  tensor, or payload-sized resident copy.
- Compute memory DSDs, `Kt`/`Nt`, pointer binder values, `sum`/`max`, `cur_`, and
  `z2_val` are entry-local.  DSR kind/id and communication/task/queue/route
  lifetime remain resident protocol.  P constructs private vecmat DSDs locally;
  R preserves the five-word resident-vecmat ABI and uses explicit numeric
  per-symbol bases, avoiding CSL array-pointer-to-u16 casts.
- M5R-1 compiled two production-derived SDK 2.10 probes with a real RPC/memcpy
  root and `.probe` fixed at `0x4000`.  In the materialized target, A2 RoPE +
  score GEMV has a 1,044-byte `.probe` and ELF SHA-256
  `372aab31dd0fd60d6127777e622418340a6e03550824ae1715a42f705c79898b`;
  F1 RMSNorm + up/gate has a 488-byte `.probe` and ELF SHA-256
  `8822570d8467f18e555598e411c4379f8e5301f43031880f990d955fefd74e14`.
  The probe validator hashes the build driver, inputs, ELF, RPC manifest, and
  readelf transcripts and rejects empty/dead-stripped roots.
- M5R-2 regenerated P/R A0–A7 and F0–F3b source regions.  Exact per-function
  local-declaration, M2 control-field, forbidden-resident-operation, numeric-R-
  binding, and deterministic-generation checks pass.  This is source-shape
  evidence only; only A2/F1 were compiled.
- Production-effective RoPE odd-lane offset `0` is preserved and remains U04;
  the intended offset `1` is not silently repaired.  Full four-page composition,
  final address equality, `__divhf3`, WSE disassembly, slot selection, closure,
  and SRAM economics remain M5R-3.
- Practical failure mode: a compile can return success with an empty custom
  section if a CSL function lacks a real RPC/runtime retention root.  A valid
  probe gate must require a nonzero fixed-address section, an exact nonzero
  `FUNC` symbol, RPC export, fresh input/driver/artifact hashes, and distinct
  ELF hashes where the probes are expected to differ.

## Implications / next actions

- [ ] M5R-3 should build one real receiver-union image, bind numeric R bases
  from its final symbols, link all four P/R pages, and check per-symbol address
  equality plus code/control-flow closure.  Do not reinstate whole-section
  identity or source-level retention scaffolds.
- [ ] Keep U04, `__divhf3`, and WSE-aware disassembly fail-closed until resolved.

## Pointers

- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/STEP3_TRACKING.zh-CN.md`
- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step3-page-regions/m5r-real-receiver-abi/`
- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step3-page-regions/m5/results/m5_fail_closed_revise.json`

