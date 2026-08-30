# Qwen3-1.7B decode M1b-S0 score-layout change

> Source audit: `origin/main@b136ab64b3f5575c72fb722fb972ef5c77f4c9fe`, reviewed 2026-08-29. The S0 code is an uncommitted Part 1 working-tree change based on that revision. No simulator or CS-3 result is claimed here.

## Concrete notation and reference values

The figure deliberately uses code identifiers first, with mathematical letters only as short aliases:

| Figure label | CSL / host identifier | Meaning | Value used in the figure |
|---|---|---|---|
| `b` | loop index over `bsz` | static request/execution-lane index | `b=0,1`; `bsz=2` |
| `g` | loop index over `gqa_group_size` | Q group sharing one K/V feature shard | `g=0,1`; `gqa_group_size=2` |
| `k` | loop index over `kv_cols` | local Q/K feature coordinate | `k=0..3`; `kv_cols=4` |
| `j` | local cache/score column | sequence cell within this physical Y row | `j=0..3` in the drawing |
| `L_b` | `current_len = position_current_length(position[b], local_py)` | current valid local cells for request `b` on this PE row | old `[2,2]`; S0 `[1,3]` |
| `C_draw` | visual stand-in for `kv_len_per_pe` | per-request, per-group physical slot capacity | `4` cells, for legibility only |

The code-derived reference is `model_config/test_sim_2x2block.json`: `Pw=16`, `P_X_BLOCK_NUM=2`, hence `P_BLOCK_SIZE=8`; `MAX_SEQ_LEN=544`, hence the real `kv_len_per_pe=68`; `bsz=2`, `gqa_group_size=2`, `kv_cols=4`, and `attn_per_pe=gqa_group_size*kv_cols=8`. The kernel asserts `kv_len_per_pe>=8`, so the drawn capacity `4` is **not** a compilable live configuration. It is only a four-cell rendering of the same dimension order.

For one request/group, the contraction shown in both panels is:

```text
QKV_tile.Q[b,g,:]          [1, kv_cols]
    × XKCache[b,:,0:L_b]   [kv_cols, L_b]
    = score_f32[b,g,0:L_b] [1, L_b]
```

The complete per-PE memory orders are:

```text
Q input:      QKV_tile Q region  [bsz][gqa_group_size][kv_cols]
K input:      XKCache slab       [bsz][kv_cols][kv_len_per_pe]
score output: score_f32 arena     [bsz][gqa_group_size][kv_len_per_pe]
```

Only K and score traverse `L_b`; Q always supplies all `kv_cols` features.

## What changed in `score_matvec_mult()`

| Property | `origin/main` scalar packed layout | M1b-S0 hybrid request-segment layout |
|---|---|---|
| Logical shape | `[lane][gqa_group][N]` | `[lane][gqa_group][current_len(b,y)]` |
| Physical boundary | one globally packed prefix | fixed request segment `G*C`; groups packed inside it |
| Group base | advanced by the preceding shared `N`-wide slots | `b*G*C + g*current_len(b,y)` |
| Per-lane extent | impossible; all lanes use the same `iter_num` | `position_current_length(position[b], local_py)` |
| Compute loop | K-outer; `@map` walks all G groups and DSR auto-advances by `N` | same `b × k` control loops and `@map(G)`; output advances by the selected request's `current_len` |
| Collective | fixed `M*G*C` reduce, relying on zeroed tail | unchanged fixed `M*G*C` reduce; every request tail is explicitly zero |
| Alpha scale | one contiguous `M*G*N` prefix | one contiguous `G*current_len` prefix per fixed request segment |

Legacy aliases retained in older notes are `M=bsz`, `G=gqa_group_size`, `C=kv_len_per_pe`, `N=iter_num`, and `y=local_py`. Prefer the code identifiers above when updating this note.

### Old function (`origin/main:decode.csl:1274-1331`)

```text
zero score[0 : M*G*C]
set every score DSD length to the one scalar N

for lane b:
  bind K slab b
  for feature k:
    @map over G query groups
    destination auto-advances by N per group
  output pointer advances by G*N

all_reduce(score[0 : M*G*C])
scale score[0 : M*G*N]
```

The left-hand figure uses `iter_num=2` for both requests. The compact score order is therefore `[b0g0:2][b0g1:2][b1g0:2][b1g1:2]`, followed by the unused tail of the full allocation. The compact physical offsets are `0, N, 2N, ...`. They are valid only because every request and every physical Y row shares the same `N`. With unequal request lengths, choosing either request's length moves the following request's physical base and no longer gives all collective participants one stable address map.

### New function (uncommitted S0 Part 1, `decode.csl:1322-1390`)

```text
zero score[0 : M*G*C]

for lane b:
  current_len = position_current_length(position[b], local_py)
  request_base = b*G*C
  bind score[request_base : request_base+current_len]
  bind K[b,:,0 : current_len]
  for feature k:
    @map over G query groups
    destination auto-advances by current_len per group

all_reduce(score[0 : M*G*C])

for lane b:
  scale score[request_base(b) : request_base(b)+G*current_len(b,y)]
```

The right-hand figure uses `current_len=[1,3]`. Every request owns eight drawn
cells (`G=2`, `C_draw=4`). Request 0 stores `b0g0` at offset 0 and `b0g1` at
offset 1, then leaves six zero cells. Request 1 always begins at global offset
8, stores `b1g0` at offsets 8–10 and `b1g1` at offsets 11–13, then leaves two
zero cells. Thus request boundaries do not depend on another request's cursor,
while groups inside one request remain packed and preserve main's DSD-vectorized
`@map(G)` operation. Unwritten request tails remain zero, so the collective
extent and ordering do not change.

`softmax_score()` and `output_matvec_mult()` use the identical
`request_base+g*current_len` group formula. Different physical Y rows may have
different group offsets because their row-local current lengths differ. This is
safe: the full score-vector all-reduce runs only among X peers on the same Y row,
where the position vector is identical; Y communication carries fixed `[bsz,G]`
maxima/sums rather than the full score arena.

## Alpha-scale placement review

The extra post-collective request loop exists because the live cells are no
longer one global contiguous prefix. The current code scales exactly the
`G*current_len(b,y)` live prefix inside each fixed request segment. Padding is
zero, so one fixed-capacity `@fmuls` over all `M*G*C` cells would be
numerically equivalent for the padding cells and would remove request-level
control. It would also perform capacity-sized arithmetic when live lengths are
small. Main itself scaled only its live `M*G*N` prefix, not the capacity tail.
There is therefore no source-only performance winner between:

1. one request-local scale per lane: `sum_b G*L_b` f32 multiplies plus `M`
   control iterations; and
2. one fixed-arena scale: `M*G*C` f32 multiplies with no request branch/rebind.

For `bsz=1`, the current request loop executes once and scales `G*L_0` cells,
which matches main's live arithmetic extent. Any performance difference is
unknown until a real CS-3 raw-TSC comparison.

Applying alpha before the X all-reduce is algebraically valid but changes f32
rounding from

```text
alpha * reduce_x(local_partial_x)
```

to

```text
reduce_x(alpha * local_partial_x)
```

and therefore is not folded into this correctness patch. The 2026-08-30 review
explicitly keeps the existing post-collective f32 alpha placement unchanged;
this is treated as intentional rather than an S0 cleanup target. Folding alpha
into the bf16 Q operand would additionally lose precision before the f32
`@fmachs` accumulation. A specialized collective could instead scale the
fully reduced f32 vector at the band root before broadcast, preserving the
reduce-then-scale order, but it would couple attention semantics to the
communication function and would still require a reviewed full-capacity or
segmented extent. Reconsidering that placement requires a separate design
review and measurement; it is not part of S0 Part 1.

## Deferred performance question

The current collective still sends the full `M*G*C` arena, exactly as main did;
neither the old globally packed live prefix nor this hybrid layout changes its
fabric DSD extent. A future optimization could try to omit zero tails (old equal
case `M*G*N`; hybrid row total `G*sum_b(L_b)`), but it needs a count-exact
segmented communication/liveness design and real CS-3 raw-TSC evidence. It is a
post-S0 TODO, not a performance result or S0 acceptance gate.

## Separate KV-placement boundary

The score change needs only a correct count of valid local cache cells. It does not establish a logical-token identity for host-seeded cells.

- Host synthetic seed: `launch.py:1524-1536,1663-1679,2168-2215` slices the full sequence capacity into contiguous Y-row blocks, then takes each row's first `plen` cells.
- Device ingress: `decode.csl:1869-1913` copies those cells to local columns `[0,plen)`.
- Decode append: `decode.csl:1283-1315` alone uses `owner_row=position%P`, `column=floor(position/P)`.

For the S0 P-aligned boundary `n=rP`, ingress installs `r` local cells on every row. At `p=rP+s`, immediately after the current append, row `y` has `r+1` cells iff `y<=s`, else `r`. That is exactly `position_current_length(p,y)`.

This is why the helper formula and the decode write address do not change merely because the audited host synthetic seed uses a different source ordering: the P-aligned boundary supplies the same **count** `r` to every physical row, and decode appends into the next free local column `r`. This is not a general statement that KV format is irrelevant. Numerical equivalence additionally requires the seeded K/V pairs to represent the intended prefix and to undergo the same permutation. A wrong token set, a K/V permutation mismatch, or a non-P-aligned ingress with unequal initial row counts can still produce wrong results even though the local bounds are safe.

## Visual

The editable source is `qwen3_1p7b-decode.m1b-s0-score-layout.excalidraw`; the checked derived rendering is `qwen3_1p7b-decode.m1b-s0-score-layout.svg`.
