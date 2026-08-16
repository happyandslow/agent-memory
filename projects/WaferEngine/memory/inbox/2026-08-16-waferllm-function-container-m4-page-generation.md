# WaferLLM function-container M4 page generation

Date: 2026-08-16

## Scope and frozen inputs

- Work is Phase 1 Step 3 M4 only; it stops before M5 link/closure audit and
  before any loader/runtime/device execution.
- WaferLLM revision remains
  `fd1c2daae37cd68706c03fc8009887ecee9900f8`.
- Frozen production `Decode/src/decode.csl` SHA-256 remains
  `88921a433a9cf205ffdacbe7c5b0ff644d27788b70fdbdf1377b6d2984bdabeb`.
- Production `Decode/` was not modified.

## M3 corrections required by page generation

- The score GEMV body at lines 510–523 belongs to A2; score scale 526–530
  belongs to A3 after the resident score reduce and before local max 532–541.
- Per-entry closure must include fresh/prebound A1 Q/K/V DSDs, A2 RoPE temp
  DSDs, A5 output DSD, and F1 z1/z2 DSDs. Stale A2 Q/K DSD requirements were
  removed.
- U04 records a frozen-source/profile conflict: production resets
  `X_odd_dsd` to the same base as `X_even_dsd` without an explicit +1 restore.
  M4 preserves source behavior and does not claim RoPE correctness; M5 or a
  focused SDK 2.10 probe must resolve it before correctness claims.
- Authoritative M3 validation passes with 25 components and 13 entry profiles.

## M4 result

Four deterministic source-link regions were generated:

- P Attention, private vecmat closure:
  `bc7d73196b7223b5d3293da77539205f815accea033d1fa7a2b195c6660d8fb8`
- P FFN, private vecmat closure:
  `416ce189475a1974858a7eab65d41862f5692cd816ba2566bd248770fd0ea835`
- R Attention, fixed-address resident vecmat direct call:
  `9505d99bde40016c2a302fec8e98aa36da8febf36e5c61e83a3cabac61d1b48d`
- R FFN, fixed-address resident vecmat direct call:
  `5b88a3d3d79a1151e185d3b38a58cb79dc8bd0907fce9bd197b6580d60dc105a`

The byte counts recorded beside these files are source-text bytes, not final
payload or SRAM bytes. P contains page-private vecmat/@map closure. R uses nine
complete 5-word byte-address ABI writes and one M5-supplied fixed target. R
removes only GEMV binder state and retains non-GEMV RMSNorm/RoPE/normalize
binder state.

All page-local helpers, entries, dispatchers, and exported retention roots use
`.m4_page`. Page sources contain no collective, route, fabric, queue, task, or
Decode continuation calls. `page_control` and the R `[5]u16` ABI object remain
M5 receiver-owned address-matched storage; no shadow receiver storage was
introduced.

## Evidence and review

- SDK 2.10 structural compile fixture PASS; ELF SHA-256:
  `a5229c76869836bb5a62a772ca152ef5057a08d07885c207a0b353dfbb426102`.
- The strict M4 validator PASSes and invokes authoritative M3 validation. It
  also checks deterministic generation, exact M2 yield IDs/continuations, P/R
  closure, all nine R tuples, patch identity, and builder idempotence.
- Claude Code using default `claude-fable-5` first returned revise-level FAIL
  for a minimal-patch ordering mismatch and incorrect empty R binder closure.
  After fixes, targeted read-only re-review returned PASS.
- Evidence grade remains S: source transform plus structural compile-only.

## Next gate

Only M5 may follow: receiver composition, common final SLOT_ADDR, final page
ELFs, call/branch/@map/compiler-helper closure, DSD/DSR/address matching,
specialization catalog, and complete receiver SRAM economics. Do not infer
transferred-page execution correctness or `net_free` from M4.

Primary artifacts:

- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/STEP3_TRACKING.zh-CN.md`
- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step3-page-regions/m4/`
