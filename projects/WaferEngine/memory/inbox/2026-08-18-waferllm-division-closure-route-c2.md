# WaferLLM division closure Route C2: owned helpers support fixed resident targets

Status: captured

Situation: a transferred Attention/FFN page needs reciprocal and inverse-square-root
code, but SDK 2.10's compiler-local `__divhf3` cannot be given an enforceable
cross-image address.  Route C2 tests whether the SDK-derived Route-B algorithms
can instead be owned in explicitly named receiver sections.

## Durable result

The exact DIV-2 helper function bodies, with only link-section ownership adapted,
compiled into stable resident targets across independently linked Attention-like,
FFN-like, receiver-only, and perturbed-receiver images:

- `div2_sdk_invsqrt_f16`: `.c2_resident_invsqrt` at `0x2800`, 148 B,
  payload SHA-256 `b710df4a6b009831f15d6f3e00e5c8ef75bc23d9d1ee790f7d17aa532948d0ad`;
- `div2_sdk_inv_f16`: `.c2_resident_inv` at `0x2a00`, 184 B,
  payload SHA-256 `d9bb55ae8f15d1895bd5318f6f8cb9b30d520819c34826142c789ae54b7e0ab2`.

Adding an unrelated 60-byte ordinary `.text` RPC root to only the receiver did
not change either fixed helper's address or payload.  All ELF symbol tables have
zero `__divhf3`; page and service sections contain named return sites for both
helpers.  Relocation tables are empty.  Verdict:
`PASS_STATIC_FIXED_RESIDENT_HELPERS`, evidence Grade E.  Without a WSE-aware
disassembler this is not complete decoded call/branch closure and is not runtime
correctness.

## Cost and comparison

The isolated receiver-vs-no-helper linked payload floor is 388 B: 148 B invsqrt
+ 184 B reciprocal + 56 B callable resident service.  In this pinned fixture
the low high-water delta is zero and the existing gap shrinks by 388 B; production
receiver economics must be recomputed.

DIV-2 and C2 use identical function bodies/algorithms, but moving addresses changes
4 encoded bytes in invsqrt and 3 in reciprocal.  The admissible contract is byte
identity across all C2 images at the same fixed addresses, not address-independent
identity with the original DIV-2 ELF.

No numerical comparison, simulator/device execution, loader/transfer runtime,
DIV-4, M6, or Phase 2 work was performed.

Evidence:

- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step3-page-regions/m5r3-division-closure-probe/div3/c2/RESULTS.md`
- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step3-page-regions/m5r3-division-closure-probe/div3/c2/summary.json`
- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/STEP3_TRACKING.zh-CN.md`

## Final disposition after DIV-4 (2026-08-18)

Route C2 remains technically eligible but is rejected for the current two-page
receiver economics. In the production-shaped comparison it reduced the aligned
slot by 256 B, but increased the permanent receiver excluding-slot floor by
424 B (P) / 440 B (R), so complete allocated receiver SRAM increased by 168 B
(P) / 184 B (R) relative to Route B. No resident-math ABI is admitted.
