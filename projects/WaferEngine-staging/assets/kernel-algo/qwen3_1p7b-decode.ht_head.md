# ht_head.csl (decode) — static 2-D vocab shard + diagonal-pair W_E gather

> Kernel algorithm walkthrough. Model `qwen3_1p7b-decode`, ref config `test_sim_2x2block_kv_varlen.json`.
> Diagram: `qwen3_1p7b-decode.ht_head.svg`. Comms taxonomy per the `cerebras-kernel-comm-patterns` skill.
> **Git state:** branch `lexu/staging/s6a-inner-pe-kv-route-a`, working tree dirty with the uncommitted
> S6a KV-retain work. `src/ht_head.csl` and `launch.py`'s head/demux regions are themselves **unmodified
> vs `fcfc8c1`** (the dirty files are `decode.csl`, `ht_tail.csl`, `kv_ingress_*.csl`, `launch_device.py`),
> so this doc describes code identical at HEAD and in the tree.

## Core idea — decode embeds ONE token per step, not a chunk

This is the headline difference from prefill's `ht_head` (the file says so itself at
`src/ht_head.csl:7-10`). Both turn token ids into `W_E` rows, but:

| | prefill `ht_head` | decode `ht_head` |
|---|---|---|
| Tokens per invocation | a whole **chunk** of prompt tokens per request | **one** sampled token per lane, per decode step |
| Where tokens come from | host, via the demux row (`token_id_buf` holds `2·reduce_len` ids) | **HT_tail, fed back on-chip** each step (`tok_bcast_color`) — the host is not in the loop after step 0 |
| Vocab layout | one shared tile **rotated** around the X band (`HEAD_WIDTH` hops, amortised over the whole chunk) | **statically 2-D sharded**: vocab on **Y**, hidden on **X** — there is **no rotation ring at all** |
| Resolution mechanism | rotate the table past every column, `compare_record` locally | vertical **gather** of the one needed `W_E` row over 4 statically-painted relay colors |
| Loop | per-chunk, per-request | per-step `while (ht_step < n_steps)`, `bsz` gathers inside each step (`:300-343`) |

Decode cannot amortise a rotation: a rotation ring costs `P_BLOCK_SIZE` hops to resolve **any** number
of tokens, which is a bargain for a chunk of hundreds and absurd for **one** token per step. So decode
inverts it — keep the table still, move the single needed row. The row lives at a runtime-computed PE
row `src_py = token_id / V_per_pe_y`, which the fabric **cannot route on** (Gate 1: no destination
field). The lawful escape used is **#1, replicate the decision**: `tok_bcast` multicasts the *same*
`bsz` token ids to **every** PE in the band, so every PE in a column independently computes the same
`src_py` and takes a branch consistent with its neighbours' (`:328-334`). Routes are painted statically
in 6 positions at compile time (`launch.py:919-953`); only *participation* is runtime.

Step 0 is special and is the only host-fed step: the host sends a **pre-embedded** `X[0]` hidden vector
for the seed tokens through the demux (`launch.py:2399-2413`), so no lookup happens at all.

## Data distribution on PEs

HT_head band = **`HT_WIDTH_tail` cols (X) × `P_BLOCK_SIZE` rows (Y)** (ref config: **6 × 8**;
`launch.py:857-858`). The embedding runs only on the **EAST `HT_WIDTH_head` columns**
(`HT_WIDTH_head = P_BLOCK_SIZE/2 = 4`, `x_local ∈ [HT_X_OFFSET=2, 6)`); the 2 west columns exist only to
match the tail's width for a uniform token connect and to relay `pre_embed_x` east at step 0
(`launch.py:548-560`; `ht_head.csl:20-23, 250-254`).

| Tensor | Sharding | Notes |
|---|---|---|
| `W_E_tile` (`:68`) | **vocab on Y, hidden on X** | PE `(x_local, py)` owns `W_E[py·V_per_pe_y : +V_per_pe_y, eff·2·dim_per_pe : +2·dim_per_pe]`, `eff = x_local − HT_X_OFFSET`. Ref: `V_per_pe_y = 24/8 = 3` vocab rows × `2·dim_per_pe = 16` features (`launch.py:464-465, 1012-1036`). |
| `token_id_buf[bsz]` (`:71`) | **replicated on every band PE** | i32 (device vocab > i16 max). Drained from `tok_bcast` by *every* column, incl. the west relay columns which discard it (`:309`, `launch.py:955-965`). |
| `embed_buf[bsz·dim_per_pe]` (`:72`) | held **only by the 2 diagonal PEs of each column** | upper-diag `py = 2·eff` gets the column's **first** `dim_per_pe`, lower-diag `py = 2·eff+1` the **second** (`:174-180`). |
| `n_steps` (`:66`) | replicated scalar, overwritten per round | host-seeded via `set_symbol_all`; with `KV_TRANSFER=1` re-read each round from an N header on the token path (`:296-299`, `launch.py:873-874`). |

**The diagonal pairing is the re-layout.** Column `eff` owns hidden features `[eff·16, eff·16+16)`;
its upper-diag PE (row `2eff`) takes the low 8 and its lower-diag PE (row `2eff+1`) the high 8. Across
`eff = 0..3` that maps row `py` → features `[py·8, py·8+8)` — exactly the **hidden Y-shard** that decode
block row 0 expects. So the gather does double duty: it resolves the lookup *and* converts
(vocab-on-Y, hidden-on-X) into (hidden-on-Y). That identity is asserted at `launch.py:564-566`
(`HT_WIDTH_head · 2 · dim_per_pe == dim`); breaking it is a wavelet-count mismatch into row 0, i.e. a
silent hang. In taxonomy terms the pairing is a **P-4 seam** (diagonal funnel re-layout), realised by
the same relay chains that do the gather rather than by a separate transpose.

## Communications + which task owns each step

**Phase 0 · `init` — derive coords, paint the two X-path routes, release the demux (`:243-283`)**
- Reads `tile_config.get_fabric_coord` and subtracts `region_origin_{x,y}` to get `head_my_x_local` /
  `head_my_py`; derives `head_is_active`, `head_my_diag_col = py/2 + x_offset`, the upper/lower diag rows,
  and the `py` parity (`:250-260`).
- Paints **`pre_embed_x_color` (id 18, C1)** per row: `WEST→EAST` west of the row's diag col,
  `WEST→RAMP` **at** it, unpainted east of it — a per-row terminating east run (`:264-268`).
- Paints **`post_embed_x_color` (id 23, C2)**: `RAMP→EAST` on a diag PE, `WEST→EAST` east of the diag col
  (`:270-275`).
- **Ready barrier (G-8-style fence):** col-0 PEs `@mov32` **1 u32 WEST** on `ht_ready_color` (**id 0**)
  (`:278-280`). This exists because C1's route is painted at *runtime* here while the demux could send
  at *load* time — without the barrier a `bsz=1` config races and stalls (`launch.py:997-1005, 2330`).
  Then `@activate(main_id)`.

**Phase 1 · `main`, per-round budget header (G-4 header on an existing channel, `:296-299`)**
- With `kv_stream_ingress != 0`, one `bsz`-wide tile is drained off `tok_recv_dsd` **ahead of** the
  tokens; slot 0 is this round's step budget `N`, which overwrites `n_steps`. HT_tail's token emitter
  produces it (`ht_tail.csl:1299-1310`). Every column drains it, so it is bit-identical everywhere —
  which is what makes the loop bound safe as a shared control value.

**Phase 2 · step 0 — host X[0] seed (P-6 p2p, no lookup) (`:301-304`)**
- Only the **diag** PEs `@fmovh(embed_buf_dsd, pre_embed_x_recv_dsd)`, draining `bsz·dim_per_pe` fp16 that
  the demux column pushed east on C1. West columns and non-diag PEs do nothing.

**Phase 3 · steps 1+ — token in, `W_E` gather out (`:305-338`)**
- `@mov32(token_id_buf_dsd, tok_recv_dsd)` on **every** column: `bsz` i32 ids arriving from the south.
  The route is a **P-2 router multicast** — `launch.py:958-960` paints `SOUTH → {RAMP, NORTH}` uniformly,
  so one emit from HT_tail fans out up the whole column; the top row terminates `SOUTH→RAMP`
  (`launch.py:961-965`).
- **Early stop (replicated branch):** if `token_id_buf[0] == STOP_TOK (−2)` every column `break`s, and
  the diag PE first floods C2 with `STOP_SENTINEL_F16 = −65504.0` so the block X-broadcast carries the
  stop to the whole pipeline (`:290-291, 315-321`). Everyone sees the same token, so everyone exits
  together — no hang.
- `embed_gather_dispatch(b, src_py, vocab_off)` per lane `b` (`:134-234`), on active columns only.

**The gather itself (`embed_gather_dispatch`, `:134-234`) — G-1 parity chain + P-5 shuttle along Y**

Four statically-painted colors, two per direction, alternating by row parity so no two adjacent routers
paint the same color: **`UP_A` (21) / `UP_B` (22)** northbound, **`DOWN_A` (8) / `DOWN_B` (9)** southbound
(`launch.py:610-611, 693-694`). `DOWN_*` are **reused K-pipe ids** — legal because the K-pipe lives on a
PE-disjoint rectangle (`launch.py:691-694`). Six painted positions, keyed on `local_py` vs the column's
diag pair (`launch.py:906-953`): P1 upper-diag, P2 lower-diag, P3/P4 south of the pair (even/odd),
P5/P6 north of the pair (even/odd).

Each of the two `dim_per_pe` halves of the needed `W_E` row is shuttled as one `@fmovh`. Four cases,
all decided from the replicated `src_py`:

| Case | Chain | What moves | Code |
|---|---|---|---|
| `src_py > lower_diag` (source south of pair) | **NORTH** on `UP_*` | source pushes both halves; interior PEs shuttle `UP_A→UP_B` (even) / `UP_B→UP_A` (odd); lower-diag forwards the upper half on `UP_A` and consumes the lower; upper-diag consumes from `UP_A` | `:152-160, 183-202` |
| `src_py < upper_diag` (source north of pair) | **SOUTH** on `DOWN_*` | mirror image, **halves emitted in reverse order** because consumer order along the chain is reversed | `:161-170, 203-221` |
| `src_py == upper_diag` | 1-hop **SOUTH** on `DOWN_B` | source consumes its half locally, pushes the other to lower-diag | `:171-175, 222-226` |
| `src_py == lower_diag` | 1-hop **NORTH** on `UP_A` | source consumes its half locally, pushes the other to upper-diag | `:176-181, 227-232` |

PEs beyond the source in the away direction are idle (`:185-186, 205-206`). Cost is
`O(|src_py − diag|)` hops per lane per step, run `bsz` times serially in the `b` loop (`:323-335`) —
i.e. the gather is **not** amortised, it is paid on every decode step. That is the price of not
rotating.

**Phase 4 · emit east (P-6 p2p into decode block row 0) (`:340-342`)**
- Both diag PEs `@fmovh(post_embed_x_send_dsd, embed_buf_dsd)` — `bsz·dim_per_pe` fp16 east on C2, which
  is the same fabric id the decode block reads as `x_input_color` (`launch.py:1171, 2323`). This fires
  on **every** step, step 0 included.

**Phase 5 · per-round re-arm (`:345-350`)**
- With `kv_stream_ingress != 0`: reset `ht_step = 0` and `@activate(main_id)`, so `main` re-reads the
  next round's `N` header and re-parks step 0 on the host `X[0]`. With `KV_TRANSFER=0` it is single-shot.

## Communication summary

| Movement | color / queue | direction | pattern | task(s) |
|---|---|---|---|---|
| ready sentinel (1 u32) | `ht_ready_color`(0) / `ready_oq`=oq5 | WEST, col 0 only | **1-wavelet barrier / route-paint fence** | `init` (`:278-280`) |
| step-0 pre-embedded X[0] | `pre_embed_x_color`(18) / `pre_embed_x_iq`=iq3 | EAST, per-row, terminating at diag col | **P-6 p2p** + per-row terminating run | `main` (`:301-304`) |
| N header + per-step tokens | `tok_bcast_color`(7) / `tok_iq`=iq2 | SOUTH→{RAMP,NORTH} up the column | **P-2 router multicast**; header = **G-4** | `main` (`:296-299, 309`) |
| `W_E` gather, northbound | `UP_A`(21)·`UP_B`(22) / iq4,iq5 · oq3,oq4 | NORTH along Y | **G-1 parity chain + P-5 shuttle** | `embed_gather_dispatch` (`:152-202`) |
| `W_E` gather, southbound | `DOWN_A`(8)·`DOWN_B`(9) / iq6,iq7 · oq6,oq7 | SOUTH along Y | **G-1 parity chain + P-5 shuttle** | `embed_gather_dispatch` (`:161-221`) |
| diag → hidden Y-shard re-layout | (carried by the same chains) | Y | **P-4 seam** (diagonal funnel) | `embed_gather_dispatch` + `launch.py:564` identity |
| embedded X east | `post_embed_x_color`(23) / `post_embed_x_oq`=oq2 | EAST into decode row 0 | **P-6 p2p** | `main` (`:340-342`) |
| early-stop flood | `post_embed_x_color`(23) | EAST | **sentinel broadcast** (rides C2 into the block X-bcast) | `main` (`:315-321`) |

Correctness is **count-exactness on a replicated branch**: every PE in a column derives `src_py` from
the *same* multicast token id, so senders and receivers along `UP_*`/`DOWN_*` agree on the wavelet count
without any handshake. A token id that reached only some PEs, or a `V_per_pe_y` mismatch, is a **silent
hang** — never an error.

## One line

Same program on every band PE; `(x_local, py)` picks a different `W_E` tile and a different role in the
relay chain. Decode replaces prefill's amortised vocab-rotation ring with a per-step vertical gather of
the one needed embedding row, and folds the (vocab-on-Y → hidden-on-Y) re-layout into the same diagonal
chains — the right trade when you embed **one** token per step instead of a chunk.
