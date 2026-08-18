# WaferLLM division closure Route C1: compiler `__divhf3` is not an enforceable resident ABI

Date: 2026-08-18

Project: WaferLLM Decode MeshJIT/function-container, Phase 1 Step 3 division-closure study.

## Durable conclusion

Route C1 preserved the existing CSL `/` expressions and tested whether the SDK
2.10 compiler-generated `__divhf3` could be shared as a fixed-address resident
callee.  In the controlled fixture, Attention-like, FFN-like, and receiver-only
images naturally linked one byte-identical 168-byte helper at `0x0b2c`
(`f9662166d0127f3be3593d96d5e82c2be798afaa1957daf339dd13616a41bdac`).
This match is emergent, not an enforceable address contract.

Both attempted placement controls were ineffective:

- `.text:512` left `.text` at `0x0038` and the helper at `0x0b2c`;
- `.text.__divhf3:12288` produced no independently placed helper section and
  also left the helper at `0x0b2c`.

Adding one ordinary resident root moved the helper to `0x0b68` and changed its
machine-code hash.  Therefore the compiler-local helper must not be admitted as
an approved external target.  Route C1 verdict is
`FAIL_CLOSED_NO_ENFORCEABLE_HELPER_PLACEMENT`, evidence Grade E.

## Receiver-floor evidence

A controlled receiver-without-helper comparison attributes 196 linked payload
bytes to this retention mechanism: 168 bytes of `.text` helper plus 28 bytes of
resident service root.  In the fixture the low-address high-water did not grow
because an existing fixed-placement gap shrank by 196 bytes.  This is not a
production SRAM-saving result and must be recomputed in the full receiver.

## Scope and next gate

No simulator/device/runtime execution, loader, C2, DIV-4, or Phase 2 work was
performed.  The next candidate, only after review, is Route C2: move the
byte-identical SDK-derived owned helper from Route B into an explicitly named,
fixed-address receiver section and audit its permanent receiver floor.

Primary evidence:

- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step3-page-regions/m5r3-division-closure-probe/div3/RESULTS.md`
- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step3-page-regions/m5r3-division-closure-probe/div3/summary.json`
- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/STEP3_TRACKING.zh-CN.md`

## Final disposition after DIV-4 (2026-08-18)

Route C1 is permanently rejected for this design. The compiler-local
`__divhf3` match was a linker coincidence, not an address ABI; an unrelated
ordinary `.text` root moved the helper. It must not appear in an approved
external-target manifest.
