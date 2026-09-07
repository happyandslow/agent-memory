# Qwen3-4B decode ATTN PE: activation buffers are allocated disjointly but only ~930 B are live at once — 2026-09-06

**Project:** wse3-performance-model
**Author:** claude (session 4b-mini-cache)
**Status:** captured

## Situation

You are hunting for more per-PE SRAM on the Qwen3-4B decode ATTN PE (2×4
blocks of 256×256, the shipped device layout), the code levers are spent, and
you are looking at the activation/scratch buffers wondering which ones can be
made to share an address. Reading `attn_layer_body` and every buffer
declaration to rebuild the lifetime picture costs about an hour; this is that
picture.

## Fact: per-phase live set (source-derived, `src/decode.csl`, 8K config)

Execution inside one layer is strictly serial, so a buffer is reclaimable
outside its phase. Bytes are the declared sizes at `MAX_SEQ_LEN=8192`, bsz 1,
`attn_per_pe=16`, `kv_cols=4`, `gqa_group_size=4`, `dim_per_pe=10`:

| phase (in execution order) | live buffers | live bytes |
| --- | --- | --: |
| RMSNorm + QKV proj + Y reduce + cast | `X_tile` 20, `X_norm`/`scratch_dim_a` 32, `QKV_f32` 100 → `QKV_tile` 48 | ~150 |
| QK-norm + RoPE + `process_kv` | `QKV_tile` 48, `X_tmp_1..4` 64, `qknorm_sum` 20, `X_fp32_buf` 40 | ~170 |
| score = Q·Kᵀ + band reduce | `QKV_tile` 48, `score_f32` 512 | ~560 |
| softmax (max reduce, exp, sum reduce) | `score_f32` 512 → `score` 256, `exp_n` 128, local max/sum 32 | **~930 (peak)** |
| Score@V + Y reduce + normalise | `score` 256, `scratch_dim_a_f32` 80, `local_sum_gqa` 16 | ~350 |
| O proj + X reduce | `scratch_dim_a` 32, `scratch_dim_b_f32` 40 | ~70 |
| residual, send Z / recv X | `scratch_dim_b` 20, `Z_tile` 20, `X_tile` 20 | ~60 |
| **request start only** (outside the layer loop) | `kv_ingress_buf` 248 — all of the above are dead here | 248 |

Sum of the separately allocated buffers is ~1,672 B while the peak live set is
~930 B. The score family (`score_f32` 4 B/elem, `score` 2 B/elem) and
`kv_ingress_buf` all scale with `kv_len_per_pe`, so the gap widens with
context: at 30K they are 1,904 / 952 / 944 B.

## [unverified] What that is worth

Never compiled or run — no linker confirmation that the packing holds and no
numerical gate. Analytical only:

- Pure aliasing (put the short-lived buffers in the softmax peak's shadow,
  including `kv_ingress_buf` over `score_f32`): ≈ 740 B at 8K, ≈ 1.4 KB at 30K.
- Plus in-place softmax (`score_f32` f32 → `score` bf16 writes back into the
  front half of the same block; the write pointer trails the read pointer, so
  forward element-wise is safe): another 256 B at 8K / 952 B at 30K.
- Combined ≈ 1.0 KB at 8K, ≈ 2.3 KB at 30K (≈ 13 capacity steps ≈ 3.3K tokens).

Aliasing costs no instructions (DSD base addresses are comptime constants);
in-place softmax changes the SIMD write-back address arithmetic and therefore
needs the re-arm/bit-identity gate before it can be called lossless.

## Relation to other captures

Not the same lever as `2026-09-05-4b-optimisation-backlog.md` § C, which lists
*chunked scores* (5.3 KB) and *ingress tile streaming* (7.1 KB) — those are
measured on the thin 64×128 layout C and reduce the buffers by processing in
pieces. This note is about the shipped 256×256 layout and about reusing
addresses without changing how anything is computed. A drainer should keep
both.

## Implications / next actions

- [ ] If pursued: alias first (cheap, no numerical risk), compile-check that
  the linker packs as intended, then decide on in-place softmax separately.
- [ ] Anyone quoting a "reclaimable activation bytes" figure should use the
  peak-live number (~930 B), not the sum of allocations (~1,672 B).

## Pointers

- `/home/lexu/wse3-performance-model/demo/qwen3-4b-decode-sram/` (s0 breakdown gives the per-category totals this refines)
- source: `demo/qwen3-4b-decode-sram/code/qwen3_4b-decode-baseline/src/decode.csl` (`attn_layer_body`, buffer declarations)
- sibling captures: `2026-09-02-qwen3-4b-per-role-sram-breakdown.md`, `2026-09-02-qwen3-4b-host-route-table-lever.md`, `2026-09-05-4b-optimisation-backlog.md`
