# ht_tail.csl — lm_head mesh-GEMV + top-K sampling, looped per generated token (decode output head)

> Kernel algorithm walkthrough. Model `qwen3_1p7b-decode`, ref config `test_sim_2x2block_kv_varlen.json`.
> Diagram: `qwen3_1p7b-decode.ht_tail.svg`. Comms taxonomy per the `cerebras-kernel-comm-patterns` skill.
> **Git state:** branch `lexu/staging/s6a-inner-pe-kv-route-a`, **uncommitted working tree** (S6a KV-retain
> work). The only working-tree delta inside `ht_tail.csl` vs `fcfc8c1` is the sim-only `dbg_logit_dump`
> VALUE-verify path (`+53` lines: `param dbg_logit_dump`, the `<simprint>` import, `dump_logits_step0`
> `:1167-1185`, its call site `:1352-1354`, and `dump_round` `:1158`, `:1418`). `launch.py` is `+316`
> lines, of which the ht_tail-facing part is the `dbg_logit_dump` gate at `launch.py:2023-2024`.

## Core idea — turn each step's hidden state into one sampled token, then feed it back

`ht_tail` is the decode pipeline's output head. Per generated token it takes the **current hidden state**
`Z` (dim-sharded, shipped west out of the last decode block), and produces **one sampled next-token id**,
which it sends **two ways**: **north** to `HT_head` (closing the autoregressive loop) and **south** through
the mux to the host (with the top-K logits).

This is the same five acts as prefill's `ht_tail`, wrapped in a **step loop plus a round loop**:

1. **Drain `Z`** — the last decode block multicasts `Z` west across the vocab columns; every tail PE taps
   its own dim shard (`tail_main` `:1320`, route painted at `:1230-1234`).
2. **Final `LlamaModel.norm`** (RMSNorm, fp32) in place on `Z` — Y-axis all-reduce of the per-batch
   sum-of-squares over the dim shards (`tail_final_rmsnorm`, `:423-486`).
3. **lm_head GEMV** — each PE does a *local* matvec `partials[V_per_pe_x, bsz] = lm_head_tile @ Z`
   (`tail_lm_head_matvec`, `:405-414`), then a **Y-axis 2-phase reduce (no broadcast)** contracts the dim
   shards → full fp32 logits land on the phase-2 root row (`tail_logits_reduce_bsz_vocab`, `:726`, called
   `:1346`).
4. **Top-K** — the root row runs a local top-K over its vocab slice (`tail_local_topk`, `:862-926`), then
   an **X-axis 2-phase merge-reduce** combines them into the global top-K (`tail_topk_mergereduce_x`,
   `:956-1079`), replicated across the root row; the X-root samples (`tail_sample_token`, `:1085-1145`).
5. **Emit twice** — every root-row column emits the sampled token **north** to `HT_head` (`:1385-1391`);
   the root-row **east-most** PE emits `{topk_val, topk_arg, sampled token}` **south** to the mux → host
   (`:1396-1401`).

Same clever reuse as prefill: the **5 reduce colors + IQ/OQ 2-6 carry both the Y-axis dim-contraction and
the X-axis top-K merge**, with the root row repainting the routes at runtime (`write_X_routes_tail`,
`:602` → `write_Y_routes_tail`, `:490`) fenced by a one-wavelet cross-column barrier (`tail_xready_color`,
`:1364-1368`) — the skill's **G-3 route-repaint + G-8 fence**. Because decode loops, this repaint/restore
pair runs **once per generated token**, not once per request.

### What decode adds over prefill's `ht_tail`

| | prefill | **decode** |
|---|---|---|
| Cadence | one-shot per request (`tail_main`, prefill `:1110`) | `while (tail_step < n_steps)` (`:1313`), then `@activate(tail_main_id)` per round (`:1422-1424`) |
| Token feedback | none (no north emit) | **north emit** to `HT_head` on `tok_bcast_color` (id 7, OQ7), every root-row column, skipped on the true last step (`:1385-1391`) |
| Budget | baked | **Design X' budget header**: 1-wavelet i32 `N` rides the Z drain ahead of step-0 `Z`, overwrites `n_steps`, and is re-forwarded south + north (`:1302-1312`) |
| Early stop | n/a | in-band **STOP-Z sentinel** (`z_slice_buf[0] < -60000`) on the drain releases every tail PE together (`:1327-1339`); `STOP_TOK = -2` flooded north + south (`:1138-1144`) |
| Local top-K | K masked-argmax passes, `O(K·V)` | **size-K min-heap + SIMD block-max prune**, `~O(V)` (`:840-926`) — the code's own `ALGORITHM NOTE` at `:855-861` says why: decode runs it *per token*, so the `O(K·V)` pass was ~45 % of the per-token budget |
| TSC anchor | 1-wavelet `kickoff_color` sentinel from demux (IQ7) | **no kickoff color**; start sampled *inside the loop* at `tail_step == warmup_cycles` (`:1316-1318`) |
| Per-round state | n/a | `done_flag` / `pred_token_buf` reset + PRNG re-seed at the top of every round (`:1290-1297`) |

## Data distribution on PEs

Tail band = **`HT_WIDTH_tail` columns (X, vocab shard) × `P_BLOCK_SIZE` rows (Y, dim shard)**, placed at
`(ht_tail_x, PLACE_Y + last_row*P_BLOCK_SIZE)` (`launch.py:2223`) — i.e. the HT band's west origin,
sharing the X column band with `HT_head` but on a disjoint Y range. Ref config: **6 × 8**.

Vocab is sharded on **X**; the hidden dim (the GEMV contraction axis) is sharded on **Y**.

| Tensor | Sharding | Notes |
|---|---|---|
| `lm_head_tile` (`:132`) | vocab on **X**, dim on **Y** → `[dim_per_pe, V_per_pe_x]` per PE | dim-outer / vocab-inner (K-outer) so the GEMV reads `K=dim` outer; host `.T`s the `(vocab,dim)` slice before upload (`launch.py:2210`), else logits scramble. Tied to `W_E` (seed 2024, `tie_word_embeddings`). ref: `[8, 4]`. |
| `z_slice_buf` (`:133`) | dim on **Y**, **replicated on X** | the hidden shard, overwritten in place by the final RMSNorm; `Z` multicasts west so every vocab column in a Y-row holds the same `dim_per_pe` slice. ref: `[bsz=2, 8]`. |
| `partials_buf` (`:136`) | vocab on **X**, per-Y **partial** (fp32) | this PE's logit slice `[bsz, V_per_pe_x]`; a partial until the Y-reduce contracts the dim shards. fp32 for HF parity. ref: `[2, 4]`. |
| `W_final_norm_tile` (`:144`) | dim on **Y**, replicated on X | RMSNorm weight slice `[dim_per_pe]` (seed 2028, `launch.py:2232-2246`). |
| `topk_val` / `topk_arg` (`:274-275`) | seeded local, then **global** on the root row | after the X merge-reduce + broadcast every root-row X-PE holds the global top-K `[TOP_K*bsz]` (round-outer / batch-inner: index `r*bsz+b`, sorted DESC). `topk_arg` is i32 (device vocab id ~18 bits). |
| `pred_token_buf` (`:268`) | root row, i32 | the sampled next-token id per lane; X-broadcast across the root row so **every** column can emit north. |
| `bi_val` / `bi_arg` (`:283-284`) | strictly local | the size-K min-heap working set for `tail_local_topk`; never touches fabric. |
| `done_flag` (`:358`) | sampling PE only | sticky per-lane EOS flag; a finished lane emits `pad_id` on every later step. |

Derived dims (ref config, from `launch.py`): `P_BLOCK_SIZE = Pw/P_X_BLOCK_NUM = 8`, `dim = 64`,
`dim_per_pe = 8`, `HT_WIDTH_head = 4`, **`HT_WIDTH_tail = 6`** (config override), `vocab_size = 24` →
`V_per_pe_x = 4`, `bsz = 2`, `TOP_K = 2` ⇒ `KB = 4`, `VAL_PAD = 0`, `VAL_WLTS = 2`, `SOUTH_PAD = 0`.
Y chain (`group_num=4`): `pe_num_per_group = 2`, `root_1st_phase = 1`, `root_2nd_phase = 5`.
X chain (`launch.py:2063-2071`): `pe_num_per_group_x = min(16, 6//2) = 3`, `group_num_x = 2`,
`root_1st_phase_x = 1`, `root_2nd_phase_x = 4`.

**Note a decode-specific geometry quirk:** because `HT_WIDTH_tail` (6) is set independently of the X-chain
root, the **sampling PE** (`root_2nd_phase_x = 4`) and the **south emitter / TSC PE**
(`x = HT_WIDTH-1 = 5`, `launch.py:2116`) are **different cells** at this config. In prefill's 2×4 ref they
coincided. The X-broadcast at `:1375-1377` is what carries the sampled id from one to the other — it is
load-bearing here, not a convenience.

## Communications + which task owns each step

**Phase 0 · setup (`tail_init`, `:1201-1283`)** — reads its wafer coord via `tile_config.get_fabric_coord`,
subtracts `region_origin_{x,y}` (`launch.py:2095-2096`) to derive `(tail_my_x_local, tail_my_py)`, derives
both chain ids (`:1210-1213`), then paints, all per-PE at runtime:
Y reduce/broadcast routes (`write_Y_routes_tail`, `:1215`); the **north** token route (`:1219-1223`, root
row `RAMP→NORTH`, rows above `SOUTH→NORTH` up to `Edge.TOP`); the **Z-drain multicast** (`:1230-1234`,
west-most `EAST→RAMP`, interior `EAST→{RAMP, WEST}`); the **south** logits route on the east-most column
only (`:1239-1245`); and the **X-phase barrier tree** on the root row (`:1249-1271`). Seeds the PRNG on the
sampling PE (`:1274-1276`), enables the TSC counter on `is_tsc_pe` (`:1278-1280`), `@activate(tail_main_id)`.

All nine of the tail's colors are compile-time painted `RAMP/RAMP` (inert) by `launch.py:2126-2131` and
overridden per-PE here — the repo's standard idiom, because painting multi-tx at compile time on a
port-constrained color confuses the SdkLayout router.

**Phase 0.5 · per-round header (G-4 budget header + G-13 scalar broadcast; `kv_stream_ingress != 0`)**
- `tail_main` `:1302-1312`: `@mov32(nstep_hdr_buf_dsd, nstep_hdr_recv_dsd)` reads **1 wavelet** off the
  *same* `z_drain_iq` (IQ0) as `Z` — every tail PE taps the multicast, so every PE gets a bit-identical `N`
  and they all loop to the same bound. This is the lawful escape from Gate 1: the control value is
  **replicated, not routed**. `N` is then re-emitted **south** to the mux (east-most root only, `:1305-1307`)
  and **north** to `HT_head` (all root-row columns, `:1308-1311`), so the mux knows when to switch to the
  TSC drain and `HT_head` loops to exactly `N`. Port budgets carry `+kv_hdr = num_rounds`
  (`launch.py:2133`, `:2177`).

**Phase 1 · drain Z (P-2 router multicast, west-flowing) — once per step**
- `tail_main` `:1320` parks on `z_recv_dsd` (extent `bsz*dim_per_pe = 16`, IQ0) until the last decode block
  ships `Z` east into `ht_tail_in_edge = Edge.RIGHT` (`launch.py:2133-2138`, color `last_result_color =
  last_rg.color("result_color")`, `launch.py:1319`). It multicasts **EAST→WEST**; the west-most PE
  terminates, interior PEs tap + forward. Each Y-row PE keeps its own `dim_per_pe` slice.
- **Early stop rides this same channel** (`:1327-1339`): the last decode block relays a STOP-Z whose
  `X[0] = NEG_INF`; because the drain is a multicast, **every** tail PE sees it at the same point in the
  loop, before any collective, and they `break` together. No extra color, no extra fence — the sentinel is
  in-band on a channel that already runs (Gate-3 step 0).

**Phase 2 · final RMSNorm (P-1 two-phase all-reduce, with broadcast)**
- `tail_final_rmsnorm` (`:423`): per batch, cast to fp32, square in place, `@fadds` to a scalar
  (`:432-451`), then **one** `tail_reduce_bsz_f32` (`:825`) → `tail_reduce_2phase` (`:732`) does a Y-axis
  2-phase chain all-reduce of the `bsz` sums **with** the broadcast leg (`do_broadcast=1`), so every Y-PE
  gets the full-dim variance. Then normalize + `@fs2h` + `* W_final_norm` in HF order (`:459-485`),
  in place over `z_slice_buf`.

**Phase 3 · lm_head GEMV + dim-contraction reduce (local matvec + P-1 two-phase reduce, no broadcast)**
- `tail_lm_head_matvec` (`:405`): purely **local** `@fmachs` GEMV (`vecmat_computation_lm`, `:383`) →
  `partials_buf` fp32. Zero comms. This is the `m = 1` case the skill's P-1 vs P-3 rule points at: decode
  holds one token, so all-reduce is the indicated pattern and Cannon would be wrong here.
- `tail_logits_reduce_bsz_vocab` (`:726`, called `:1346`): reuses `tail_reduce_2phase` with the *longer*
  extent `bsz*V_per_pe_x` and **no** broadcast — full logits land only on `root_2nd_phase`.
  Same fabric DSDs, different `@set_dsd_length`: the **widen-an-existing-payload** idiom, done safely —
  `:733-734` resets **both** base address *and* length on entry, and `:736-743` derives the fabric DSDs as
  fresh `const` locals rather than mutating module-scope ones (the `csl-module-dsd-length-carryover` trap).
- *(working tree, sim only)* `dump_logits_step0` (`:1167`) prints the root row's full fp32 vocab shard at
  step 0 of each round via `<simprint>`, before the top-K discards all but K. Comptime-folded away on
  device builds.

**Phase 4 · top-K (root row only; P-1 two-phase reduce with a merge combiner, on repainted X routes)**
- `write_X_routes_tail` (`:602`, called `:1360`) repaints reduce colors 1-5 from Y to X. It handles the
  root-at-chain-edge case with a 1-tx fan-out (`:684-695`) so the broadcast never emits off the tail edge.
- **G-8 fence** (`:1364-1368`): `root_2nd_phase_x` sends one wavelet on `tail_xready_color`; every other
  root column blocks on it before any X send, so no column emits an X-mode wavelet into a neighbor still
  painted for Y. The barrier's route tree is **static** (painted once in `tail_init`, never repainted) —
  which is exactly the skill's requirement that a repaint fence live on a separate, never-repainted color.
- `tail_local_topk` (`:862`): seeds a size-K **min-heap** with the first K logits, then scans the rest in
  `LT_BLOCK = 8`-wide blocks, reducing each block to its max with a 3-level SIMD `@fmaxs` tree
  (`:885-887`); a block whose max ≤ the running K-th-largest is skipped wholesale. Survivors fall back to
  scalar insert + `lt_heap_sift_down` (`:840`). Heap-sort in place → DESC (`:913-919`). Padded vocab is
  excluded by `v_real = V_per_pe_x - vocab_pad_count` (`:865`; per-column `vocab_pad_count` set at
  `launch.py:2040-2044`, zero at this config). Output is bit-identical to a plain scan.
- `tail_topk_mergereduce_x` (`:956`): **X-axis 2-phase reduce** whose per-hop combine is a K-list
  2-pointer merge (`topk_merge_local`, `:930`), **not** a sum. Each hop recvs `KB` fp16 values (`@fmovh`,
  `KB/2` u32 on the wire) + `KB` i32 ids (`@mov32`, `KB` u32) into `recv_topk_*`, merges into the running
  `topk_*`, sends it on. Final broadcast (`:1072-1078`) replicates the global top-K to every root-row X-PE.
  Then `write_Y_routes_tail` restores Y routes (`:1379`) **before the next step**.

**Phase 5 · sample, feed back, emit**
- `tail_sample_token` (`:1085`, `root_2nd_phase_x` only): temperature scale → fp32 softmax over the sorted
  top-K → top-p nucleus truncation (keep ≥ 1) → categorical draw via `random.random_f32` → `pred_token_buf`.
  EOS handling (`:1118-1127`): the eos token is emitted on the step it is sampled; `done_flag` makes every
  *later* step emit `pad_id`. When all lanes are done and `enable_early_stop != 0`, `pred_token_buf` is
  overwritten with `STOP_TOK = -2` (`:1138-1144`), which floods `HT_head` (X-path STOP) and tells the host
  to stop.
- **P-2 X-broadcast** of the sampled id (`:1373-1378`) on the broadcast color → every root-row column.
- **North emit** (`:1385-1391`, `tail_is_token_emitter`, i.e. the whole root row): `bsz` i32 on
  `tok_bcast_color` (id 7, OQ7), `RAMP→NORTH` then `SOUTH→NORTH` transit to `Edge.TOP`
  (`launch.py:2142-2149`). Skipped when `tail_step == n_steps-1` (no further token is consumed), which is
  what makes the tail's emit count match `HT_head`'s drain count exactly. All `HT_WIDTH_tail` columns emit
  so the head's full-width port connect stays uniform.
- **South emit** (`:1396-1401`, east-most root cell only): `TOP_K*bsz+VAL_PAD` fp16 values (`@fmovh`) +
  `TOP_K*bsz` i32 ids (`@mov32`) + `bsz` sampled tokens, plus a dummy u32 when `SOUTH_PAD == 1` — the D2H
  egress requires an **even** per-step wavelet count, and `SOUTH_PAD` in the kernel (`:248`) must match
  `south_pad` in the host (`launch.py:2168`). Transits down the east column to `Edge.BOTTOM` → mux → host.
  Emitted on **every** step including the last, so the host's receive count is exactly the budget.

**TSC timing (`is_tsc_pe`, the east-most root cell `(HT_WIDTH-1, root_2nd_phase)`, `launch.py:2116`)**
- Start: sampled at the **top of the iteration where `tail_step == warmup_cycles`** (`:1316-1318`), before
  any work for that iteration. End: at `tail_step == n_steps-1` (`:1405-1414`), or at the STOP-Z break
  (`:1328-1337`). Both are packed into one 8-u32 burst (slots 0-2 start, 4-6 end, 3/7 pad) and
  **async-emitted on OQ0 after that step's south blob** — no separate color, port, or stream; the mux
  drains 8 extra per round (`launch.py:2172-2173`).
- ⚠️ **Load-bearing measurement callout.** The timing span is `tail_step == warmup_cycles` → last decode
  step, both *inside* the step loop. Everything before the loop body — **the per-round KV injection, the
  budget-header exchange, `tail_init`, and step 0 (prefill's token)** — is **outside the timing window**.
  `warmup_cycles = WARMUP + 1` (`launch.py:245-246`; ref config `WARMUP = 1` ⇒ `warmup_cycles = 2`), and
  the comment at `launch.py:244` states the intent: step 0 = prefill is always excluded. So a decode
  latency/throughput number from this counter is **steady-state per-token decode only**. It does **not**
  include KV-cache reload cost, and comparing a KV-retain run against a no-reuse run on this metric alone
  will show the reuse saving as *absent*, because the thing that changed was never inside the window.
  Any KV-transfer cost must be measured host-wall or with a separate counter.

## Communication summary

| Movement | color / queue | axis / direction | pattern | task / fn |
|---|---|---|---|---|
| budget header `N` (per round) | `z_drain_color` / IQ0 | X, **E→W** multicast | **G-4 header + G-13 replicated scalar** | `tail_main` `:1302-1304` |
| `Z` drain into tail (per step) | `z_drain_color` (= last block's `result_color`) / IQ0 | X, **E→W** multicast | **P-2 router multicast** | `tail_init` `:1230-1234` / `tail_main` `:1320` |
| STOP-Z sentinel | same channel, in-band | X, **E→W** multicast | in-band sentinel (no new color) | `tail_main` `:1327-1339` |
| RMSNorm sumsq reduce | reduce 1st/2nd + bcast (ids 1-5) / IQ·OQ 2-6 | Y (dim), reduce **+ bcast** | **P-1 two-phase all-reduce** | `tail_reduce_bsz_f32` `:825` → `tail_reduce_2phase` `:732` |
| lm_head dim-contract | same reduce colors / IQ·OQ 2-5 | Y (dim), reduce **no bcast** | **P-1 two-phase reduce** (widened DSD) | `tail_logits_reduce_bsz_vocab` `:726` |
| X-phase barrier | `tail_xready_color` / IQ·OQ 1 | X, 1 wavelet | **G-8 fence** (static tree) | `tail_main` `:1364-1368` |
| top-K merge | same reduce colors, **repainted Y→X** / IQ·OQ 2-6 | X (vocab), reduce **+ bcast** | **P-1 two-phase reduce, merge combiner** (G-3 repaint + G-8 fence) | `tail_topk_mergereduce_x` `:956` |
| sampled-token spread | `broadcast_color` (5) / OQ·IQ 6 | X, 1→many | **P-2 broadcast** | `tail_main` `:1373-1378` |
| **sampled token → HT_head** | `tok_bcast_color` (7) / OQ7 | Y, **RAMP→N** then S→N to `Edge.TOP` | **P-6 p2p north emit** (the autoregressive feedback edge) | `tail_main` `:1385-1391` |
| top-K + token → host | `logits_south_color` / OQ0 | Y, **RAMP→S** then N→S to `Edge.BOTTOM` | **P-6 p2p south emit** → mux → host | `tail_main` `:1396-1401` |
| `N` re-forward south / north | `logits_south_color` OQ0 / `tok_bcast_color` OQ7 | Y, both directions | **G-4 header** re-emit | `tail_main` `:1305-1311` |
| TSC burst (8 u32) | `logits_south_color` / OQ0, async | Y, S | piggyback on an existing channel (Gate-3 step 0) | `tail_main` `:1405-1414`, `:1328-1337` |

**No collective crosses the tail band**, and nothing here is keyed or data-dependent in its *routing* —
every destination is a compile-time function of the PE's own coordinates, and every runtime-varying count
(`n_steps`) is a **replicated** value delivered by multicast, never a routed one. Correctness is
**count-exactness**: both ends of every reduce/emit derive the same wavelet count from
`local_px` / chain ids / `V_per_pe_x` / `TOP_K` / `n_steps`; a mismatch is a **silent hang**, not an error.
The three places that are easy to break are the north-emit skip on the last step (`:1388` vs the host's
`max_output_len_worst` port budget at `launch.py:2147`), `SOUTH_PAD` (`:248` vs `launch.py:2168`), and the
`+kv_hdr` / `+8·num_rounds` port allowances.

## One line

Same program on every tail PE; the wafer coord picks each PE's vocab slice (X) and dim slice (Y).
`ht_tail` does a local lm_head GEMV, contracts the dim shards with a Y-axis two-phase reduce, then
**reuses those very reduce colors — repainted to X and fenced — to merge per-column top-K lists into one
global top-K**, samples a token on one PE, and sends it **north to `HT_head` to close the autoregressive
loop** and **south to the host** — once per generated token, once more per round, with the whole KV
injection sitting outside the TSC timing window.
