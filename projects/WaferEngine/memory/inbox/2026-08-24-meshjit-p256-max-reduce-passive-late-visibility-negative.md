# MeshJIT P=256 max-reduce passive late visibility is negative — 2026-08-24

**Project:** WaferEngine
**Author:** codex
**Status:** captured

## What happened / finding

- Situation: the full P=256 Attention max-only RPC reproducibly returned a uniform partial max `15.015625`, while the same input's max-plus-subtract RPC returned the correct `19.90625`. This raised the testable hypothesis that `all_reduceMax_bsz` returns before its final broadcast becomes visible in `local_max`.
- A same-artifact CS-3 experiment preserved both controls: original max-only returned `15.015625` on all 65,536 PEs, and original shifted returned `19.90625` with zero shifted-score mismatches. All condition score tensors were raw-bit equal.
- After the production max reduction returned, one noinline scalar-load helper sampled the same `local_max` after cumulative communication-free local-loop counts 0, 1, 8, 64, 512, and 4096. Every snapshot and the final live storage remained raw-bit-identical `15.015625` on all PEs; no PE changed at any boundary.
- Verified negative result: ordinary elapsed PE-local work does not make the wrong partial max become globally correct within the tested window. The simple passive late-write mechanism is not supported.
- The wrong value is structurally meaningful: it is the local maximum at `py=180` and the maximum of Y group 11 (`py=176..191`); the true maximum is `19.90625` at `py=231`, group 14. A uniform coherent wrong group maximum is not evidence of mixed stale payloads or gradual per-PE convergence.
- Still unverified: shifted's `@map(fsubh_func, local_max_dsd)` may create a DSD/CE dependency or ordering edge, its DSD/DSR setup may perturb state, or code layout may alter the collective path. Do not promote any of these to root cause without a same-artifact dependency-consumer A/B.

## Implications / next actions

- [ ] Compare, after the same max reduction and without subtract: scalar sample; shifted-style DSD/DSR setup only then scalar sample; identity `@map` consumer of `local_max` then scalar sample.
- [ ] Stop using "more delay may let the final max arrive" as the leading explanation unless a dependency-specific probe supplies new evidence.
- [ ] Preserve an exact original max-only control in every further instrumented artifact; if it stops returning `15.015625`, classify the probe as a Heisenbug.

## Pointers

- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-runtime-validation/full-baseline-late-visibility/cs3_evidence/2026-08-24/REPORT.md`
- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-runtime-validation/full-baseline-late-visibility/cs3_evidence/2026-08-24/offline_results.json`
- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-runtime-validation/full-baseline-late-visibility/cs3_evidence/2026-08-24/device_arrays_f16.npz`
- `projects/WaferEngine/memory/inbox/2026-08-23-meshjit-p256-full-baseline-fence-negative.md`
