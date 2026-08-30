# Qwen3-1.7B decode M1b-S0 Score@V memory traversal

> Source audit: `origin/main@b136ab64b3f5575c72fb722fb972ef5c77f4c9fe`, reviewed 2026-08-29. The S0 implementation shown here is an uncommitted working-tree change. No simulator, CS-3 timing, or performance result is claimed.

## Concrete notation

| Short label | Code identifier | Meaning | Figure value |
|---|---|---|---|
| `b` | loop over `bsz` | static request / execution lane | `b=0,1`; `bsz=2` |
| `g` | loop over `gqa_group_size` | Q-head group | `g=0,1`; `gqa_group_size=2` |
| `d` | column in `kv_cols` | local V/output feature | `d=0..3`; `kv_cols=4` |
| `C` | `kv_len_per_pe` | physical row capacity in a lane's V slab and score group capacity | drawn as `C_draw=4`; audited test config uses `68` |
| `N` | `iter_num` on `origin/main` | one scalar row-local length shared by every request | `N=2` |
| `L_b` | `position_current_length(position[b], local_py)` | row-local current length for request `b` | `L=[1,3]` |

The audited reference config has `bsz=2`, `gqa_group_size=2`, `kv_cols=4`, `attn_per_pe=8`, `P_BLOCK_SIZE=8`, and `kv_len_per_pe=68`. The four-row capacity is only a drawing.

## Tensor orders

```text
left input, score:  [bsz][request segment G*C]
                     group g is packed at request_base(b) + g*length(b)
right input, V:     [bsz][kv_len_per_pe][kv_cols]
numerator output:   [bsz][gqa_group_size][kv_cols] f32
fused reduce arena: [numerator bsz*attn_per_pe][denominator bsz*G] f32
```

For each `(b,g)`:

```text
score[b,g,0:length] [1, length]
    @ XVCache[b,0:length,:] [length, kv_cols]
    = output[b,g,:] [1, kv_cols]
```

## Before and after

On `origin/main`, `left_vector_dsd` is bound once to the globally packed score prefix with length `N`, then incremented by `N` after every group. Each group must replay request `b`'s V slab from its start because the source DSR advances by one V row per score element. `out_vector_dsd_f32` advances by `kv_cols` after every group.

S0 binds the score DSD once at the complete arena base. Inside request `b`, the groups remain packed and `@increment_dsd_offset(left_vector_dsd, L_b)` walks them; after the G groups, one remainder increment skips `G*(C-L_b)` to the next fixed request segment. Output increments are unchanged. The V DSD is bound once at the complete lane-slab arena base and advances by one fixed `C*kv_cols` slab after each request.

The implemented working-tree traversal puts `if (current_len > 0)` outside the group loop. It increments score by `current_len` and output by `kv_cols`. Both invariant lengths are set before the group loop:

```text
right_matrix_dsd length = kv_cols
out_vector_dsd_f32 length = kv_cols
```

The former repeated group-local length assignments and V DSD base rebinds have
been removed. The V DSD template stays at the current lane's slab base; each
group reloads that unchanged template into the source DSR, replaying the slab
from row zero, while `.save_address=true` advances only the DSR during the
`@map`. For `bsz=1`, the fixed descriptor setup is again outside the request
loop; the remaining structural difference from main is the request-level
position derivation/branch and dynamic score length. Runtime impact remains
unknown until real CS-3 raw-TSC measurement.

## Fused normalization boundary

`local_sum_gqa_group_f32[bsz*G]` is copied immediately after the `bsz*attn_per_pe` numerator cells. `all_reduce_bsz_attn_sum_fusion()` reduces the fixed total

```text
bsz * (attn_per_pe + gqa_group_size)
```

across Y. After the collective, `fmuls_softmax_func` divides each fixed output vector by its matching global denominator. None of these communication or output dimensions depends on `L_b`.

## Visual

The editable source is `qwen3_1p7b-decode.m1b-s0-score-v-layout.excalidraw`; the derived rendering is `qwen3_1p7b-decode.m1b-s0-score-v-layout.svg`.

## Verification status

The local SDK 2.10 compile-only gate passed after the shared `current_len`
saturation and descriptor refactor. Claude Code Fable 5 independently
re-reviewed V replay through per-group DSR loads, fixed lane-slab/request
increments, zero-row contribution, fused collective ABI, and `bsz=1`
equivalence and returned `APPROVED` on 2026-08-30. No simulator or CS-3 run is
claimed.
