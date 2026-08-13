# WSE CSL pageability audit

- Source: `/home/lexu/WaferEngine/models/qwen3_1p7b-e2e-pdSeparate/src/decode`
- Evidence: **E**
- Entry: `decode.csl::decode_layer_body`
- Functions: 46
- Classification counts: abi-pinned=13, resident-thunk-required=8, unsupported-current-loader=25

> Source spans are navigation aids, not linked bytes or SRAM savings.

## Entry call sequence

The order below is lexical direct-call order, not a full runtime state machine.

1. `rmsnorm_x`
2. `xq_matvec_mult`
3. `xk_matvec_mult`
4. `xv_matvec_mult`
5. `comm_mod.all_reduce_bsz_dim_QKV_fusion`
6. `cast_f32_to_bf16`
7. `comm_mod.reconfig_allreduce_axis`
8. `qk_norm_q_k`
9. `apply_rope_q`
10. `apply_rope_k`
11. `process_kv`
12. `score_matvec_mult`
13. `softmax_score`
14. `output_matvec_mult`
15. `o_matvec_mult`
16. `attn_residual_add`
17. `rmsnorm_z`
18. `up_matvec_mult`
19. `gate_matvec_mult`
20. `comm_mod.all_reduce_bsz_ffn_dim_ZZ_fusion`
21. `ffn_gate_silu`
22. `ffn_swiglu_mul`
23. `down_matvec_mult`
24. `ffn_residual_add`

## Fabric admission snapshot

- View: `decode_layer_body` with 30 stages
- Lifetime-free colors in this view: c0, c7, c8, c9, c10, c11, c12, c13, c14, c15, c16, c17, c18, c21, c22, c23
- Queues free/unbound for every stage: none
- Queues that are free/unbound in at least one stage: none
- Color-audit labels: 6 total; asserted=2

A free color does not provide a loader channel when no queue is free. Integration needs a proved drain + queue rebind + route repaint/fence, or a compatible existing transport.

## Candidate triage

| Candidate | class | src lines | linked B | mem DSD | fabric DSD | DSR ids | calls/maps |
|---|---|---:|---:|---:|---:|---|---|
| `decode.csl::rope_kernel` | abi-pinned | 62 | 600 | 8 | 0 | 1,1,1,2,2,2,3,3,3,4,4,4,5,5,5,6,6,6 | 0/0 |
| `decode.csl::process_kv` | abi-pinned | 48 | — | 4 | 0 | — | 0/0 |
| `decode.csl::qk_norm_phase1` | abi-pinned | 38 | 296 | 2 | 0 | 1,1,1 | 0/0 |
| `decode.csl::ffn_gate_silu` | abi-pinned | 27 | — | 9 | 0 | — | 0/0 |
| `decode.csl::vecmat_computation_f32` | abi-pinned | 19 | 236 | 3 | 0 | 1,1,1 | 0/1 |
| `decode.csl::cast_f32_to_bf16` | abi-pinned | 10 | — | 2 | 0 | 1,1 | 0/0 |
| `decode.csl::attn_residual_add` | abi-pinned | 7 | — | 3 | 0 | 1,1,1 | 0/0 |
| `decode.csl::ffn_residual_add` | abi-pinned | 7 | — | 2 | 0 | 1,1,1 | 0/0 |
| `decode.csl::ffn_swiglu_mul` | abi-pinned | 7 | — | 3 | 0 | 1,1,1 | 0/0 |
| `decode.csl::fmulh_softmax_func` | abi-pinned | 7 | — | 0 | 0 | 1,1 | 0/0 |
| `decode.csl::zero_f32` | abi-pinned | 6 | — | 1 | 0 | — | 0/0 |
| `decode.csl::fsubh_func` | abi-pinned | 5 | — | 0 | 0 | 1,1 | 0/0 |
| `decode.csl::gemv_static_step_f32` | abi-pinned | 4 | — | 0 | 0 | 1,1,1 | 0/0 |
| `decode.csl::run_matvec_f32` | resident-thunk-required | 14 | — | 2 | 0 | — | 1/0 |
| `decode.csl::xk_matvec_mult` | resident-thunk-required | 6 | — | 0 | 0 | — | 2/0 |
| `decode.csl::xv_matvec_mult` | resident-thunk-required | 6 | — | 0 | 0 | — | 2/0 |
| `decode.csl::gate_matvec_mult` | resident-thunk-required | 5 | — | 0 | 0 | — | 2/0 |
| `decode.csl::up_matvec_mult` | resident-thunk-required | 5 | — | 0 | 0 | — | 2/0 |
| `decode.csl::xq_matvec_mult` | resident-thunk-required | 5 | — | 0 | 0 | — | 2/0 |
| `decode.csl::apply_rope_q` | resident-thunk-required | 2 | — | 0 | 0 | — | 1/0 |
| `decode.csl::apply_rope_k` | resident-thunk-required | 1 | — | 0 | 0 | — | 1/0 |
| `comm_lib/comm_pe.csl::all_reduce_bsz_f32` | unsupported-current-loader | 82 | 432 | 1 | 10 | 2 | 0/0 |
| `comm_lib/comm_pe.csl::all_reduce_bsz_g` | unsupported-current-loader | 82 | 424 | 1 | 10 | 2 | 0/0 |
| `comm_lib/comm_pe.csl::all_reduceMax_bsz_g` | unsupported-current-loader | 81 | 424 | 1 | 10 | 2 | 0/0 |
| `comm_lib/comm_pe.csl::all_reduce_bsz_dim` | unsupported-current-loader | 80 | 424 | 1 | 10 | 2 | 0/0 |
| `comm_lib/comm_pe.csl::all_reduce_bsz_dim_QKV_fusion` | unsupported-current-loader | 80 | 420 | 1 | 10 | 2 | 0/0 |
| `comm_lib/comm_pe.csl::all_reduce_bsz_ffn_dim_ZZ_fusion` | unsupported-current-loader | 80 | 424 | 1 | 10 | 2 | 0/0 |
| `decode.csl::rmsnorm_kernel` | unsupported-current-loader | 71 | 844 | 4 | 0 | 1,1,1 | 2/0 |
| `decode.csl::decode_layer_body` | unsupported-current-loader | 62 | 3600 | 0 | 0 | — | 24/0 |
| `decode.csl::score_matvec_mult` | unsupported-current-loader | 57 | 544 | 4 | 0 | 1,1,1 | 3/1 |
| `comm_lib/comm_pe.csl::all_reduce_bsz_g_seq_len_kv_head_scoped` | unsupported-current-loader | 54 | 284 | 1 | 6 | 2 | 0/0 |
| `comm_lib/comm_pe.csl::all_reduce_qk_kv_head_scoped` | unsupported-current-loader | 53 | 284 | 1 | 6 | 2 | 0/0 |
| `decode.csl::softmax_score` | unsupported-current-loader | 50 | 892 | 5 | 0 | 1,1,1 | 2/3 |
| `decode.csl::output_matvec_mult` | unsupported-current-loader | 44 | 484 | 3 | 0 | 1,1,1 | 3/1 |
| `decode.csl::qk_norm_phase3` | unsupported-current-loader | 34 | 784 | 3 | 0 | 1,1,1 | 1/0 |
| `comm_lib/comm_pe.csl::reconfig_allreduce_axis` | unsupported-current-loader | 16 | 44 | 0 | 0 | — | 3/0 |
| `decode.csl::qk_norm_q_k` | unsupported-current-loader | 10 | — | 0 | 0 | — | 3/0 |
| `comm_lib/comm_pe.csl::write_X_kv_head_routes` | unsupported-current-loader | 8 | 60 | 0 | 0 | — | 1/0 |
| `comm_lib/comm_pe.csl::write_X_routes` | unsupported-current-loader | 8 | 92 | 0 | 0 | — | 1/0 |
| `comm_lib/comm_pe.csl::write_Y_routes` | unsupported-current-loader | 8 | 92 | 0 | 0 | — | 1/0 |

JSON contains all 46 functions; this table shows 40.


## Missing gates

- controlled baseline vs body-absent relink (grade A)
- holder/source and receiver/slot address + payload-byte identity audit
- receiver candidate-absence proof and bit-exact dynamic execution (grade D)
- full baseline-vs-dynamic receiver SRAM accounting
- on-device load/use timing after correctness (grade T)

## Interpretation

A source classification only selects experiments. It does not prove payload identity, receiver candidate absence, correct slot execution, or net SRAM saving.
