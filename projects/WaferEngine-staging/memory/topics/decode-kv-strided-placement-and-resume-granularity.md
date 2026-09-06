---
summary: On origin/main b136ab64, synthetic host KV seeding slices contiguous sequence-capacity blocks per Y row, while decode appends use row-round-robin placement. The safe S0 invariant is the per-row valid-cell count at P-aligned starts, not a shared logical-position permutation.
tags: [waferengine-staging, m1, m1b-s0, decode, kv-layout, score-layout, correction]
---

# Decode KV placement, current-length invariant, and score layout

This topic corrects the 2026-08-07 claim that host-seeded KV and decode-appended KV visibly use the same `t -> (t mod P, t/P)` transform in the current host code. The correction was source-audited on 2026-08-29 against `origin/main@b136ab64b3f5575c72fb722fb972ef5c77f4c9fe` and the uncommitted M1b-S0 Part 1 working tree based on that revision.

## Corrected placement boundary

The current synthetic host path does **not** contain an explicit logical-prefix transpose from `[0,1,2,...]` to row streams `[0,P,2P,...]`, `[1,1+P,1+2P,...]`, and so on.

- `launch.py:1524-1536` uses `shard_3d(..., swap_xy=True)` for K. Reshaping the full sequence-capacity axis gives physical Y row `y` one contiguous capacity block whose source columns are `[y*C, (y+1)*C)`, where `C = kv_len_per_pe`.
- `launch.py:1663-1679` builds the synthetic full-capacity K/V shards. V uses the analogous contiguous sequence block on Y.
- `launch.py:2168-2215` (`_repack_kv_band`) takes the first `plen` local cells from every already-sharded row and serializes them. It does not perform a second sequence permutation.
- `decode.csl:1869-1913` receives the per-row K/V tile and copies it into local cache columns `[0, plen)`.
- In contrast, `decode.csl:1283-1315` appends a newly decoded token at `owner_row = position % P` and `write_column = floor(position/P)`.

Consequently, source documentation must not infer a seeded cell's logical global-token identity solely from its `(physical_y, local_column)`. The live synthetic fixture defines physical cache contents; a real upstream producer must supply PE-local tiles that match the same physical cache contract, or a separately reviewed ingress repack must make the logical-to-physical mapping explicit.

## Why `position_current_length()` is count-safe at the S0 boundary

S0 keeps the P-aligned prefix rule. Let a lane start at `n = rP`, and let its current token position be `p = rP + s`, with `0 <= s < P`.

1. Ingress installs exactly `r` contiguous local cache cells on every physical Y row.
2. Decode positions `rP, rP+1, ..., rP+s` append to rows `0,1,...,s`, respectively, all at local column `r`.
3. Immediately after `process_kv()` writes the current token, row `y` therefore has `r+1` valid local cells when `y <= s`, and `r` otherwise.
4. `1 + floor((p-y)/P)` evaluates to exactly those two cases (with the helper's `p < y -> 0` guard for the generic lower boundary).

This proves the **local valid-cell count** used by score/softmax/value traversal. It does not prove that the host synthetic seed performed a logical-token round-robin permutation.

Example with `P=4`, `n=8`, and enough capacity (`C>=3`): ingress leaves two local cells on each row. The first decode token `p=8` is appended at `(row 0, column 2)`, so the post-write lengths are `[3,2,2,2]`. For `p=9`, row 1 receives column 2 and the lengths become `[3,3,2,2]`.

## Score layout change in M1b-S0 Part 1

`origin/main`'s `score_matvec_mult()` (`decode.csl:1274-1331` at `b136ab64`) uses one scalar `iter_num = N` and packs every `(lane, GQA-group)` score immediately after the preceding `N`-wide slice. Its physical slot base therefore depends on the common live extent. That representation cannot encode unequal lane lengths while preserving a fixed collective address map.

The revised uncommitted S0 Part 1 version (`decode.csl:1322-1390`) uses a fixed
`G*C` physical segment per lane/request and packs that request's groups inside
the segment, with:

```text
request_base(b) = b*G*C
current_len(b,y) = position_current_length(position[b], y)
group_base(b,g,y) = request_base(b) + g*current_len(b,y)
```

The function now:

1. zeroes the full `M*G*C` f32 arena;
2. restores the `b × k` control loops and uses one `@map(G)` so the groups of
   request `b` occupy `[request_base, request_base+G*current_len)`;
3. leaves the rest of each fixed request segment zero;
4. performs the unchanged fixed-extent `M*G*C` KV-head collective; and
5. scales only each request's contiguous `G*current_len` prefix.

The fixed request base prevents one lane's position from changing another
lane's physical score address. Packing only within a request preserves main's
DSD-vectorized traversal over `G`; softmax and Score@V use the same dynamic group
base. Zero request tails keep the fixed collective structurally valid. The full
score all-reduce is confined to X peers on one physical Y row, which derive the
same length vector; cross-Y reductions contain fixed `[lane,group]` scalars, so
row-local group offsets need not match across Y.

The score collective remains fixed `M*G*C`, as it was on main. Omitting zero
request tails is a separate post-S0 performance TODO requiring a count-exact
communication/liveness contract and real CS-3 raw-TSC evidence; no speedup is
currently claimed.

## Durable visual

- Editable source: `assets/kernel-algo/qwen3_1p7b-decode.m1b-s0-score-layout.excalidraw`
- Derived SVG: `assets/kernel-algo/qwen3_1p7b-decode.m1b-s0-score-layout.svg`
- Source-backed walkthrough: `assets/kernel-algo/qwen3_1p7b-decode.m1b-s0-score-layout.md`

## Historical note

The earlier 2026-08-07 finding and its promoted summary said both ingress and append used the same visible strided transform. That statement is superseded by this audit. P-aligned resume remains useful, but the current S0 proof rests on equal **per-row counts** at the ingress boundary, not on the removed placement claim.

## Updates — 2026-08-29: bounds safety is not content equivalence

Keeping `position_current_length()` unchanged means only that the P-aligned ingress count and the decode append address compose without a hole or collision: `n=rP` installs `r` cells per row, and decode position `rP+s` writes column `r` on row `s`. It does **not** mean arbitrary loaded-KV formats produce the same attention result. Semantic equivalence still requires the intended K/V pairs, identical K and V permutation, and compatible RoPE-bearing K values. The updated score-layout visual now draws Q, K, and score memory orders separately and uses code-derived identifiers/values rather than unexplained `M/G/C/N` notation.

## Updates — 2026-08-29: restore request-local DSD packing early

The first S0 implementation draft assigned every `(request,group)` a fixed
`C`-wide slot. That was numerically valid but changed QK from `b × k` plus
`@map(G)` into explicit `b × g × k` control loops. The reviewed replacement
fixes only request boundaries (`b*G*C`) and packs groups at stride
`current_len` within each request. This keeps unequal requests isolated while
restoring the original group-vectorized DSD operation before more consumers and
tests depend on the less efficient draft layout.
