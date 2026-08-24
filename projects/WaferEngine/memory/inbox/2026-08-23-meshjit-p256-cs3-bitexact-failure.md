# MeshJIT P=256 CS-3 bit-exact failure — 2026-08-23

**Project:** WaferEngine
**Author:** codex
**Status:** captured

## What happened / finding

- Situation: validating the Attention→FFN shared-slot implementation at the real Llama-8B/4K geometry (`P=256`, `dim=4096`, `seq_len=4096`, `ffn_dim=14336`, `bsz=1`) against the corrected static baseline on physical CS-3.
- The transferred-code protocol itself passed fail-closed: catalog H2D equaled holder D2H; both Attention and FFN slot readbacks matched their padded page hashes; each page completed `loaded → terminal → released`.
- Raw-f16 comparison failed. `attention_X_norm_tile` and `attention_QKV_tile` were bit-exact, but the first divergent checkpoint was `attention_score`: at flat index 0 baseline was `0x0bba` (`0.0002357959747314453`) and dynamic was `0x0bb8` (`0.00023555755615234375`); 923,904 score elements differed. Final Z had 959,744 differing u16 values; its own first difference was baseline `0xf806` versus dynamic `0xf805` at flat index 0.
- [unverified root cause] The first-divergence boundary aligns with a source-level semantic substitution: baseline softmax normalization uses production `1.0 / cur`, whereas the Attention page uses `m4_math.inv(cur)`. FFN SiLU already calls the fixed-address resident slash-division wrapper at byte address 11296, but Attention softmax does not. This is the leading explanation for why P=8 passed while P=256 exposed reciprocal rounding differences; confirm with a patched P=256 device rerun.
- Cloud archive audits matched local economics: baseline 25 specializations at 26,252 B allocated / 26,256 B high-water; dynamic 73 receiver specializations at 31,668 B allocated / 42,056 B high-water. Dynamic resident-fdiv closure passed for all 73 receivers.

## Implications / next actions

- [ ] Route Attention softmax reciprocal through the same fixed resident production-division service, regenerate all artifacts from the P=256 config, and rerun the complete CS-3 baseline/dynamic 11-checkpoint comparison.
- [ ] Do not claim P=256 shared-slot computational correctness from protocol PASS alone; the authoritative result is `FAIL_BITWISE_MISMATCH` until the rerun passes.

## Pointers

- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-runtime-validation/results/p256_cs3_20260823_summary.json`
- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-runtime-validation/runs/p256-real-20260823-v1/device_compare_result.json`
- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-runtime-validation/runs/p256-real-20260823-v1/device_dynamic_trace.jsonl`
- `projects/WaferEngine/memory/topics/meshjit-code-relocation.md`
