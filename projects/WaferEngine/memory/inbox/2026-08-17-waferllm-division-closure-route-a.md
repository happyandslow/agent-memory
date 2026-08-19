# WaferLLM division closure Route-A probe — 2026-08-17

**Project:** WaferEngine
**Author:** codex
**Status:** drained 2026-08-19 into `memory/topics/meshjit-code-relocation.md` and `plan.md`

## What happened / finding

- Situation: M5R-3 had 182 page-specialization records whose `.m4_page` code
  targeted a 168-byte slot-external `.text::__divhf3`. Named return sites did
  not identify which of the four source-level divisions caused the escape.
- A final SDK 2.10, 1-PE, compile/link-only matrix isolated the four sites with
  an exported `probe(seed:i16)`, one mutable input element, and an observable
  `unblock_cmd_stream` terminator. Each successful case has exactly one
  `.probe`-bearing compute ELF at `0x4000`; memcpy halo ELFs are excluded by
  section evidence rather than filename.
- D0, RMSNorm `cur / 4096`, links without `__divhf3`. D1
  `1/sqrt(cur+eps)`, D2 softmax `1/sum`, and D3 SiLU final division each have
  one `.probe` return site to the same 168-byte `.text::__divhf3` at `0x0b08`.
- SDK 2.10 accepts `math.invsqrt_f32`, `math.invsqrt_f16`,
  `math.invsqrt`, `math.inv`, and `math.inv_f16`. It rejects
  `math.reciprocal_f32` and `math.rcp_f32` with
  “module does not contain the requested symbol”.
- Exact Route-A compile shapes remove the named division-helper escape:
  RMSNorm `math.invsqrt(cur/4096+eps)` has a 176-byte `.probe`; softmax
  `math.inv(sum)` is 200 bytes; SiLU `z*math.inv(1+denominator)` is 212
  bytes. None has a named `__divhf3` target or return site.
- Evidence grade is E only. No numerical/special-value comparison, production
  page relink, transferred-page execution, or WSE-aware disassembly was done.
  Absence of named symbols is not a complete call/branch/back-edge proof.
- Probe fixture failures worth preserving: missing `--channels 1` stops before
  CSL parsing; scalar-to-`[*]` exports fail before the expression; cslc output
  outside its bound cwd can report success without host ELF; RPC-only export
  and a task root can still allow dead arithmetic writes. The working shape
  follows existing M5R probes: seed argument + mutable write +
  `unblock_cmd_stream` + `--memcpy`.

## Cause analysis

- The page escape is caused by compiler lowering, not by an explicit source
  call in Attention or FFN. Dynamic f16 division in D1/D2/D3 lowers to the
  compiler runtime helper `__divhf3`. That helper is linked into ordinary
  `.text` rather than the page region, so loading only `.m4_page` leaves the
  call target behind.
- D0 behaves differently because its denominator is the compile-time constant
  4096. SDK 2.10 can strength-reduce or inline that operation; the isolated
  final ELF has no `__divhf3` target or return site.
- M5R-3 linked the helper independently in each phase composition. Attention
  and FFN therefore received different composition-local addresses rather than
  one receiver ABI address. Empty relocation tables do not repair this:
  transferred page bytes would still encode a target that is neither carried
  in the slot nor proven equal to a receiver target.
- SDK `math.inv*`/`math.invsqrt*` use a different lowering path. In the exact
  isolated Route-A cases, all named code remains in `.probe` and there is no
  named `__divhf3` return site. This explains why Route A removes the known
  escape, but it does not prove bitwise equivalence to source `/` or complete
  machine-code closure without WSE-aware disassembly.
- The retention/output-path failures were probe-method failures, not math
  results. The final evidence is valid only because the RPC seed prevents
  constant folding, `unblock_cmd_stream` makes the result path observable,
  output stays inside the compiler-bound cwd, and the audit selects the sole
  `.probe`-bearing compute ELF instead of memcpy halo ELFs.

## Evidence hierarchy

1. Full-page failure: M5R-3 records 182 canonical page-specialization escapes
   from `.m4_page` to a 168-byte `__divhf3` in `.text`. This proves the
   construction blocker but does not attribute source expressions.
2. Isolated attribution: final D0–D3 linked ELFs distinguish constant division
   from the three dynamic f16 divisions. Each successful case has a nonempty
   `.probe@0x4000` and one compute ELF selected by section evidence.
3. Candidate repair: exact RMSNorm, softmax, and SiLU Route-A linked ELFs have
   no named `__divhf3` target/return site. This is Grade E symbol/section
   evidence, not numerical or transferred-page correctness.
4. Reproducibility anchors: final build SHA-256
   `0dfde1172c694188aa0235cde74045acec7eb8446785a009ab9e4bef0759d25c`;
   deterministic validation SHA-256
   `1592cf2f07dd6ef2152d5359f008cceb27ec6baeeb9978a6a982379c4f19fdb0`;
   manifest SHA-256
   `a50eaf00d49822c9ceefa31565db072fbaaea61637924d2af777caf4a299c1f7`.

## Implications / next actions — analyzed 2026-08-18

- [ ] Do not immediately rewrite M4/M5R-3 around Route A. Route A is the
  leading compile/link candidate, but it changes the arithmetic implementation
  and has no numerical/special-value proof.
- [ ] Next active milestone should remain DIV-2, as an independent comparator
  and fallback: build an owned page-private reciprocal/invsqrt helper with no
  CSL `/` and no dependency on `math.inv*`/`math.invsqrt*`. First establish an
  authoritative implementation source (documented builtin, auditable inline
  assembly, or SDK-derived implementation); do not invent an approximation.
- [ ] DIV-2 admission gates: exact D1/D2/D3 replacement shapes compile; helper
  and all named return sites/targets lie in `.m4_page`; no `__divhf3` or other
  unapproved slot-external code target; report helper duplication and page
  bytes. Stop after this probe; do not modify production Decode.
- [ ] DIV-3 remains necessary because it is the only planned route that may
  preserve the current `/` semantics without changing the math algorithm.
  C1 should test whether the compiler's existing `__divhf3` can be isolated and
  address-matched across Attention, FFN, and receiver images. If not, C2 moves
  the byte-identical DIV-2 owned helper from page-private to fixed-address
  resident ownership.
- [ ] DIV-4 performs the actual decision: relink P/R × Attention/FFN for
  Route A, DIV-2 page-private B, and eligible DIV-3 resident C; compare page
  bytes, common slot capacity, permanent receiver floor, fixed gaps,
  complete-image high-water, external targets, and specialization variants.
  Only then select the implementation.
- [ ] Numerical validation is a separate later gate. At minimum compare
  rounding and f16 special values for Route A/B/C before execution correctness;
  Step 3 compile/link evidence alone cannot select a numerically different
  implementation for production.
- [ ] Obtain WSE-aware disassembly before claiming complete executable closure.
- [ ] Keep U04 RoPE odd-offset correctness separate and unresolved.

## Pointers

- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/STEP3_TRACKING.zh-CN.md`
- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step3-page-regions/m5r3-division-closure-probe/div1/RESULTS.md`
- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step3-page-regions/m5r3-division-closure-probe/div1/results/div1_summary.json`
- Final build result SHA-256:
  `0dfde1172c694188aa0235cde74045acec7eb8446785a009ab9e4bef0759d25c`
- Final deterministic validation SHA-256:
  `1592cf2f07dd6ef2152d5359f008cceb27ec6baeeb9978a6a982379c4f19fdb0`

## Final disposition after DIV-4 (2026-08-18)

The checklist above is historical and has been completed. Production-shaped
DIV-4 relinked Route A/B/C2 across P/R x Attention/FFN and matched receivers.
Route A is now the default static implementation policy: it has zero named
page-to-`__divhf3` targets and the same aligned slot/complete receiver
allocation as Route B (P 4,352 B / 20,524 B; R 4,096 B / 20,644 B).

This preference is for integration simplicity, not SRAM. Route B remains the
fail-closed fallback if SDK lowering/hash/target evidence drifts, future
WSE-aware closure fails, or Route A fails numerical comparison with the frozen
slash expressions. Numerical equivalence remains unproved.
