# WaferLLM function-container D1 minimum-loader decomposition — 2026-08-18

**Project:** WaferEngine  
**Author:** codex  
**Status:** captured

## What happened / finding

- Situation: after Attention/FFN page regions pass static Step 3 admission, it
  is easy to undercount the next receiver floor by calling D1 “one memcpy”, or
  to overcount it by importing the full page ABI/dispatcher too early. The
  design requires `D1 = D0 + direct-to-slot loader/completion/overwrite state`
  and forbids a second payload-sized receive buffer.
- D1 is now decomposed into controlled receiver images: `D1a_transport` adds a
  direct slot mem DSD, fixed-count fabin DSD, IQ/color binding and synchronous
  receive entry; `D1b_completion` adds one u16 status and local
  `EMPTY/EVICTABLE -> LOADING -> READY`; `D1c_overwrite` adds the overwrite
  precondition and a `mark_evictable` seam. Only D1c is the official D1.
- The active Route-A/P contract fixes one slot at `0x1a00`, 4,352 B / 1,088
  u32. Attention is 4,188 B plus 164 B inert tail; FFN is 2,276 B plus 2,076 B
  inert tail. Both transfers send the complete slot, so receiver D1 needs no
  variable length or tail-clear code.
- The minimum baseline uses synchronous `@mov32`; completion is local to each
  receiver PE and therefore adds no completion task. Global all-receiver
  rendezvous, holder OQ drain and post-page quiescence are not implied by that
  local completion and remain D3/Phase-1-Step-9 obligations.
- The old xq proofs used a payload-sized `code_dst_dummy` to construct a DSD
  before rebasing it to the slot. D1 rejects that pattern. Its first compile
  gate is a DSD whose real backing object is the one `.m4_page` slot, with no
  second `>=4,352 B` receiver object.
- The provisional transport is color 1, receiver IQ2 and holder OQ2 with a
  static route/no queue rebind. Production source currently uses colors 5–9
  and IQ/OQ3–7; the same color1/queue2 scheme passed an isolated real xq
  simulator and P=4 physical CS-3 proof. This is not production admission:
  `csl-color-audit` fail-closed because old WaferLLM Decode has no `launch.py`,
  so a read-only harness adapter and machine-readable occupancy/reuse ledger
  remain mandatory.
- Holder catalog cost is whole-wafer overhead, not receiver saving: two padded
  arrays alone are at least 8,704 B per holder, before sender code/state and
  rectangular filler placement. The current Step-3 20,524-B audit receiver is
  not D0; D0 must be relinked from `A_both + one exact slot`.

## Implications / next actions

- [ ] Build the controlled ladder `D0 -> D1a -> D1b -> D1c` with identical
  config/link conditions and report complete-image marginal deltas, sections,
  task table and fixed gaps.
- [ ] Prove direct-to-slot DSD retention with no payload-sized shadow buffer,
  no second slot and no Attention/FFN body in the receiver.
- [ ] Adapt `csl-color-audit` read-only probing to the WaferLLM
  `compile.py`/`launch_sim.py` harness before calling color1/IQ2/OQ2 admitted.
- [ ] Keep D2 fields/invoke/command arena and D3 continuation/quiescence runtime
  out of D1. When D2 is built, ensure there is one authoritative status storage
  rather than a permanent loader-status/page-status duplicate.
- [ ] Stop after D1c final-link/accounting and discuss before D2.

## Pointers

- Decomposition:
  `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step4-common-floor/D1_DECOMPOSITION.zh-CN.md`
- Machine-readable contract:
  `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step4-common-floor/manifests/d1_decomposition.json`
- Validation:
  `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step4-common-floor/results/d1_decomposition_validation.json`
- Historical dynamic loader proof:
  `/home/lexu/WaferLLM/MeshJit-Decode/mirror-xq-phase/README.md`
- Authoritative design:
  `/home/lexu/WaferLLM/MeshJit-Decode/FUNCTION_CONTAINER_DESIGN.md`
