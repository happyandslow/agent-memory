# WaferLLM division closure Route-B probe — 2026-08-18

**Project:** WaferEngine  
**Author:** codex  
**Status:** drained 2026-08-19 into `memory/topics/meshjit-code-relocation.md` and `plan.md`

## Finding

- DIV-2 evaluated a page-private owned reciprocal/inverse-square-root closure
  independently of the SDK `<math>` import. The implementation was derived
  from the installed SDK 2.10 SIF, not from a locally invented approximation.
- The authoritative embedded sources are `csl-libs/math.csl` SHA-256
  `ef7233d3f2a43be553b512d0579ce284030f448a68b78b7b933814c48c2410c0`
  and `csl-libs/math/internal.csl` SHA-256
  `3d1813198bec5677534e92aaf27674cb2d5af585ea2e5f7757a1b07abb80c942`.
  The source subset retains SDK `fdivsh` special-value handling, `fnorm`, the
  Newton iterations, polynomial coefficients, sign restoration, and fscale.
- Seven SDK 2.10, 1-PE, compile/link-only probes passed. Generated source does
  not import `<math>` and contains no CSL slash operator.
- The owned named helpers are 148 bytes for `div2_sdk_invsqrt_f16` and 184
  bytes for `div2_sdk_inv_f16`, 332 bytes total. Both are in `.probe`.
- Full expression sizes are: RMSNorm 208 bytes, softmax reciprocal 228 bytes,
  and SiLU 264 bytes. Against the DIV-1 Route-A controls, the differences are
  +32, +28, and +52 bytes respectively.
- The combined isolated helper closures are 408 bytes for Attention and 444
  bytes for FFN. These include the probe entry expressions and are not
  production M4 payload sizes.
- No DIV-2 page ELF has a named `__divhf3` target or return site. Every named
  `.probe` return target resolves to a function in `.probe`. A 76-byte
  `.text::__ashlsi3` remains in the complete memcpy/system image, but no named
  `.probe` return site targets it, so it is outside the measured page call
  closure.
- Evidence grade remains E: there was no numerical/special-value execution,
  WSE-aware disassembly, production M4/M5R-3 relink, loader, or transferred-page
  execution.

## Cause analysis

- The production dynamic f16 slash expressions lower to compiler
  `.text::__divhf3`. Route B avoids that lowering by owning the SDK math
  runtime subset in the page and using the SDK's explicit `fdivsh` special-case
  instruction plus arithmetic refinement.
- Route B changes code ownership relative to Route A: the two helper bodies
  are explicit page-private functions instead of implementation reached through
  an imported SDK math module. The algorithm is SDK-derived in both routes.
- Route B still does not preserve the current production slash-expression
  semantics. It may differ in f16 rounding or exceptional cases. The only
  planned no-math-change candidate remains DIV-3 C1, which attempts to isolate
  and address-match the compiler's existing `__divhf3`.
- The first DIV-2 build driver printed FAIL even though all seven compiles
  returned zero: it counted all six layout/memcpy ELFs instead of the unique
  `.probe`-bearing ELF. That was a tooling failure. Final validation selects
  the page ELF by section evidence, as DIV-1 did.
- Rejecting every compiler helper anywhere in the complete image was also too
  broad. Closure ownership is determined by page return/call targets; unrelated
  memcpy infrastructure is recorded but not charged to the page closure.

## Evidence anchors

- Probe root:
  `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step3-page-regions/m5r3-division-closure-probe/div2/`
- Machine summary:
  `results/div2_summary.json`
- Human report: `RESULTS.md`
- Manifest SHA-256:
  `fd2323faf666be7ef69299d8802c77eb144eb96cec3b812d025f3f2caa579f51`
- Build-result SHA-256:
  `f6118b1bf640a6aefa474b26a89376124ecd54e66f93150ce035c2da6480c656`
- Deterministic validation SHA-256:
  `2f093b37d8715687b88bcace2f66222df96a8100184918dd473d75383825367e`
- Summary SHA-256:
  `42576049016accac98847813ac8287a89e61c87664ea6f7a0f69e16d94ef89de`
- `cslc` wrapper SHA-256:
  `e49dca08a7a77f86269128a44fe7689cae223946c62dbd678e375037517610f3`

## Next action

- Stop after DIV-2 and review the result before starting DIV-3.
- DIV-3 C1 should first test the no-math-change path: isolate the compiler's
  current `__divhf3`, fix it at one address in Attention, FFN, and receiver
  images, and measure its permanent receiver code/gap cost.
- If C1 is impossible, DIV-3 C2 should place the byte-identical DIV-2 owned
  helper at a fixed receiver address. C2 changes ownership but does not preserve
  production slash semantics.
- DIV-4 must compare Routes A/B/C only after all three have final-link evidence:
  page bytes, common slot capacity, receiver floor, fixed gaps, complete image
  high-water, external targets, and specialization variants.
- Numerical and special-value equivalence remain separate mandatory gates before
  selecting any math-changing route for production.

## Final disposition after DIV-4 (2026-08-18)

The next-action sequence above is historical and has been completed. Route B
passed production-shaped named-target closure with both helpers inside
`.m4_page`. Its aligned slot and complete receiver allocation are identical to
Route A, so it is retained as the explicit-ownership fail-closed fallback, not
the default. It is selected if Route A's SDK lowering/hash/target evidence
drifts or Route A fails numerical or future machine-code closure gates.
