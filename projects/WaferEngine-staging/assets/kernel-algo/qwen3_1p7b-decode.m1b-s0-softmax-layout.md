# Qwen3-1.7B decode M1b-S0 softmax memory traversal

> Source audit: `origin/main@b136ab64b3f5575c72fb722fb972ef5c77f4c9fe`, reviewed 2026-08-29. The S0 implementation shown here is an uncommitted working-tree change. No simulator, CS-3 timing, or performance result is claimed.

## Concrete notation

| Short label | Code identifier | Meaning | Figure value |
|---|---|---|---|
| `b` | loop over `bsz` | static request / execution lane | `b=0,1`; `bsz=2` |
| `g` | loop over `gqa_group_size` | Q-head group sharing one K/V head | `g=0,1`; `gqa_group_size=2` |
| `C` | `kv_len_per_pe` | physical score capacity per group inside one request segment | drawn as `C_draw=4`; audited test config uses `68` |
| `N` | `iter_num` on `origin/main` | one scalar row-local score length shared by every request | `N=2` |
| `L_b` | `position_current_length(position[b], local_py)` | row-local current score length for request `b` | `L=[1,3]` |
| `slot` | `b*gqa_group_size+g` | fixed `[bsz][gqa_group_size]` max/sum index | `0..3` |

The audited reference config has `bsz=2`, `gqa_group_size=2`, `kv_cols=4`, `attn_per_pe=8`, `P_BLOCK_SIZE=8`, and `kv_len_per_pe=68`. The four-cell capacity is only a legible drawing of the same order; it is not a compilable config.

## Before: one global packed prefix

`origin/main` stores the live score cells as one contiguous prefix:

```text
score_f32 allocation: [bsz * gqa_group_size * kv_len_per_pe]
live logical view:    [bsz][gqa_group_size][iter_num]

offsets with N=2:
b0g0=0, b0g1=2, b1g0=4, b1g1=6
```

For max and sum, main binds `score_f32_slice_dsd` once, gives it length `N`, and walks all `bsz*G` slots with `@increment_dsd_offset(..., N, f32)`. That works because every slot has the same width.

## After: fixed request segments, packed groups inside each request

S0 gives request `b` a fixed physical segment of `G*C` cells:

```text
request_base(b) = b * G * C
group_base(b,g) = request_base(b) + g * L_b
```

With `L=[1,3]`, request 0 uses two cells in segment `[0,8)`, and request 1 uses six cells in segment `[8,16)`. The max/sum outputs remain fixed `[bsz][G]` arrays and the Y max collective remains exactly `bsz*G` f32 values.

The implemented S0 traversal is:

```text
fill every max slot with -inf (one DSD operation)
bind score source DSD once at score_f32[0]
for b:
  L = current_len(b, local_py)
  if L > 0:                         // branch once per request
    set source DSD length to L
    load source DSR once with save_address=true
    for g:
      reduce the next DSR extent directly into max[b,g]
  advance the DSD template by fixed G*C

repeat the same traversal for sum after one DSD fill with 0
```

The DSR's saved address advances by `L` after each reduction, so the G
reductions reuse descriptor metadata while consuming consecutive packed groups.
The module-scope DSD template itself does not move with that DSR traversal; one
explicit fixed `G*C` increment moves it to the next request segment. Direct
pointer-result overloads of `@fmaxs` and `@fadds` remove the intermediate
`max_f32`/`sum_f32` copy used by the earlier implementation. Runtime impact
remains unknown until measured with real CS-3 raw TSC cycles.

`L_b` is zero exactly when `position[b] < local_py`. That can occur on physical
Y rows ahead of a very short sequence. For example, at absolute position zero,
row 0 appends the current token while rows `1..P_BLOCK_SIZE-1` contain no local
sequence cell and contribute max `-inf`, sum `0`, and zero Score@V numerator.
For the approved nonzero P-aligned ingress boundary `position>=P_BLOCK_SIZE`,
every Y row already has at least one seeded cell, so `L_b>0` on every row. A
zero local length is therefore a valid sequence-partition boundary, not an
inactive lane or EOS state.

## Exp and cast

`softmax_exp_slot()` still receives an explicit `group_base`, because it handles a scalar alignment prefix, SIMD-4 tiles, and a scalar tail for each group. The final f32-to-bf16 cast can remain one contiguous `G*L_b` request-prefix cast. Neither operation touches the request-capacity tail.

## Communication boundary

- QK score all-reduce: fixed `bsz*G*C` f32 cells across X peers inside one KV-head band.
- Softmax max all-reduce: fixed `bsz*G` f32 cells across Y.
- Denominator sum: not reduced here; it is packed behind Score@V numerators and reduced later.

Different Y rows may use different local `L_b` and therefore different local score addresses. That is safe because full score vectors are not reduced across Y; only the fixed `[bsz,G]` max/sum identities cross Y.

## Corrected transient typo

An accidental working-tree edit changed the max-path assignment target to the
undefined identifier `s`. It was isolated to that single occurrence and was
corrected back to `score_f32_slice_dsd` before the compile gate.

## Visual

The editable source is `qwen3_1p7b-decode.m1b-s0-softmax-layout.excalidraw`; the derived rendering is `qwen3_1p7b-decode.m1b-s0-softmax-layout.svg`.

## Verification status

The local SDK 2.10 compile-only gate passed after `current_len` saturation and
the hot-path DSD/DSR refactor. Claude Code Fable 5 independently re-reviewed the
one-load saved-address reductions, direct result pointers, empty-row DSD fills,
descriptor bounds, and collective participation and returned `APPROVED` on
2026-08-30. No simulator or CS-3 run is claimed.
