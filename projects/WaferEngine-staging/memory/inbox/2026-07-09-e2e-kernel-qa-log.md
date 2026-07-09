# qwen3_1p7b-e2e kernel Q&A log — 2026-07-09

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured

Running log of a code-reading session over `models/qwen3_1p7b-e2e` (session
`e2e-kernel-qa`). Decode CSL read directly; prefill + `launch.py` via subagents.
One `## Q<n>` section per question asked. Append, don't rewrite.

---

## Q1 — How is HT_head fed, and what colors carry prefill's first token + KV cache into decode?

### Finding

**Correction to a working assumption.** Only the **KV cache** crosses from
prefill to decode on-chip. The **first token does not.** There is no fabric path
of any color from `pf_ht_tail` to decode's HT_head.

- Prefill's sampled first token exits south: `pf_ht_tail` → `pf_mux` →
  `pf["logits_stream"]` → **host** (`launch.py` `runtime.receive(pf_blob)`).
  It is read, printed, and never sent back to the device.
- Decode's step-0 input X is **host-computed**, not prefill's token:
  `launch.py:~3006-3028` builds `host_x_f16 = W_E_full[cfg["token_ids"]]`
  (`token_ids` defaults to `[0]*bsz`, seed-2024 mock W_E) and sends it as
  `x_step_buf_u32` on `x_stream` into decode's demux.
- So the two halves are fused in **KV state only**. Decode begins generating
  from a config-chosen token, unrelated to the token prefill just sampled. A
  true fused e2e continuation would need either a host hop or a new on-chip
  token wire from `pf_ht_tail` north into decode's HT_head.

**Decode HT_head feed colors** (ids from `launch.py:535-585`):

| Wire | Color id | From → To | When |
|---|---|---|---|
| `pre_embed_x_color` (`c1_color`) | **18** | host → `x_demux` → HT_head west edge | step 0 only |
| `tok_bcast_color` | **7** | decode `ht_tail` root row → HT_head bottom edge | steps 1+ |
| `post_embed_x_color` (`c2_color`) | **23** | HT_head diag PE → decode row_0 west | every step |
| `ht_ready_color` | **0** | HT_head col=0 → demux (1-hop barrier) | init |
| `UP_A/UP_B`, `DOWN_A/DOWN_B` | 21, 22, 8, 9 | HT_head internal W_E gather chain | steps 1+ |

HT_head at step 0 does **no** embedding lookup — it just drains the host's
pre-embedded X on c1 into `embed_buf`. From step 1 it does the real 2-phase
`W_E` gather driven by token ids arriving on color 7 from decode's own HT_tail.
`DOWN_A/DOWN_B` (8, 9) are **aliases of `kpipe_a/b_colors[3]`**.

**KV cache path, prefill → decode (colors 17 / 21):**

| Segment | Region | Code | Colors |
|---|---|---|---|
| A. gather + transform | prefill block region | `prefill.csl` `start_kv_transfer` / `kv_step` states 0-3; `comm_pe.csl` `kv_sweep`, `kv_col_emit`, `kv_paint_col_chain` | sweep W **18/19**, sweep E **20/22** |
| B. north shift | prefill → relay seam → decode | `comm_pe.csl` `kv_north_shift`; `relay.csl` (no tasks, `build_relay` paints SOUTH→NORTH transit) | **17 / 21** |
| C. decode ingress | decode block region | `decode.csl` `kv_ingress` / `kv_ingress_phase`; `comm_pe.csl` `kv_flush_then_init`, `kv_oq7_empty` | **17 / 21** on IQ7/OQ7, then rebound to `broadcast_color` (5) |

Parity: even fabric rows send on 21 / recv on 17; odd rows swap at runtime
(`kv_ingress` reads `get_fabric_coord(Y)`). Relay also reserves color **22** at
RAMP/RAMP with no traffic. 17 aliases a K-pipe id and 21 aliases `UP_A_color`;
`launch.py:576` asserts these only ever coexist at X-disjoint coordinates
(strips / HT band vs block columns).

**Two side findings:**

1. `standalone-vs-integrated-kernel-parity` is **partly stale**. e2e `decode.csl`
   is md5 `05cc76d4` (note pins `71d80bba`) and now HAS Qwen3 QK-Norm +
   fp32-accumulate GEMV (`@fmachs`). Serving gaps (multi-round `round_reset`,
   EOS `STOP_THRESHOLD`, runtime-varlen prefill, chunked prefill) still hold.
   One numerics gap survives: e2e decode `softmax_score` exponentiates in
   **bf16** (`@map(fast_exp, score_dsd, score_dsd)`), keeping only the
   denominator f32; standalone runs exp/sum/normalize fully in f32. Prefill's
   softmax IS full-f32.
2. `tools/csl_color_audit` **cannot currently audit e2e**, in both directions:
   default `--ref origin/main` raises ProbeError (the `test_sim_2x2blk_kv_prof*`
   configs are untracked), and `--worktree` raises CoverageError at
   `src/decode/decode.csl:1414` — the raw `@set_config` on
   `PERF_COUNTER_CONTROL` in `kv_prof_enable()`. The standalone decode kernel
   audits fine. This is the tool refusing rather than under-reporting.

### Implications / next actions

- [ ] Decide whether fused e2e should carry prefill's first token to decode
      on-chip (new wire `pf_ht_tail` → decode HT_head), or whether the host hop
      is acceptable. Today decode's output is not a continuation of prefill's
      prompt — relevant to any end-to-end accuracy claim.
- [ ] Teach `tools/csl_color_audit/parse_csl.py` the raw `@set_config(addr/word_size, val)`
      form so the KV-profiler code is covered; do NOT widen `_TRIPWIRE_BENIGN`.
- [ ] Update `standalone-vs-integrated-kernel-parity` at the next maintain pass:
      the numerics half of the gap is mostly closed; record the bf16-exp residue.

### Pointers

- `models/qwen3_1p7b-e2e/launch.py:535-585` (decode color ids), `:921-953`
  (HT_head ports), `:2026-2036` (connects), `:2863-2878` (`build_relay`),
  `:3006-3028` (host X seed).
- `models/qwen3_1p7b-e2e/src/decode/ht_head.csl`, `decode.csl:1424-1463`
  (`kv_ingress`), `src/prefill/prefill.csl:805-845` (`kv_step`).
- Topology reference (other session, unverified but consistent with code):
  `assets/prefill-decode-transfer/e2e-topology-full.svg`.
- Relates to [[prefill-decode-transfer-bandwidth]] (A/B/C segments),
  [[standalone-vs-integrated-kernel-parity]].

---

## Q2 — Why are the demux and the inter-col strip missing from `e2e-topology-full.svg`, and how does the strip work?

### Why they're hard to find in the diagram

- **The demuxes ARE drawn**, dashed and 1 PE wide: `x_demux (x2 · y1–256)` and
  `pf_demux (x4–131, y514)`. At 645-column scale a 1-PE column is a hairline.
  Legend: "Dashed = mux/demux I/O plumbing."
- **The strips are NOT drawn, and the SVG's column labels hide them.** Each
  decode row region is `region_width = Pw + 2` placed at
  `region_place_x = PLACE_X - 1` (`launch.py:1018-1019, 1235`). For the real
  512 config `PLACE_X = HT_WIDTH_tail + 4 = 132`, so a row region spans
  **x131 … x644**: west strip at **x131**, block columns x132–643, east strip
  at **x644**.
  - The SVG labels x0–131 as "west band" — but **x131 is the decode west strip**,
    part of the row region, not the HT band.
  - **x644 is never drawn.** It is the `+1` in `total_w = PLACE_X + Pw + 1 = 645`.
- Worse for findability: in the shipped **2×2** config the *only real* strip is
  the **east** one (x644). Per `strip_realness()` (`launch.py:203-226`), with
  `P_Y_BLOCK_NUM=2`: row 0 (even, first) → `real_west=False, real_east=True`;
  row 1 (odd, last) → `real_east=True, real_west=False`. So all real inter-block
  strip traffic lives in a single undrawn column at the extreme east edge.
- The two **fake** west strips are not dead — they are compile-time wire:
  row 0's carries `post_embed_x_color` (23) into the block (`launch.py:1335`),
  row 1's carries `result_color` out to HT_tail (`launch.py:1256`).
  `dispatch_init_task` returns early on them (`decode.csl:1484-1487`).

### How the inter-col strip (K-pipe) works

The strip is a **corner turn**, and it exists only for **inter-ROW** block hops.
Intra-row hops (block 0 → block 1 within a row) need no strip: they ride
`inter_block_a/b_color` (19/20) straight across adjacent block columns.

Snake order: even rows run east, odd rows run west. At a row's tail the pipeline
must jump to the next block row, which is a Y hop the horizontal snake can't do.

1. **Block → strip.** In the sender block, only `local_px == root_2nd_phase`
   (root col) drives `inter_block_send_z`; `INTER_A/B` routes forward
   `DIR_IN → DIR_OUT` along every row `ly`, so each of the `P_BLOCK_SIZE` rows
   delivers `B = bsz*dim_per_pe` wavelets into the strip PE at that `ly`
   (strip q0 IQ).
2. **K-pipe south.** `KPIPE_K = 8` interleaved pipes share the one strip column.
   PE at `ly` belongs to pipe `k_own = ly % 8`, own-cell index `i_own = ly / 8`,
   `M_PER_PIPE = P_BLOCK_SIZE / 8`. Each pipe has a color pair
   `(kpipe_a[k], kpipe_b[k])`; consecutive own-cells alternate rx/tx across the
   pair so neighbours never send on the same color. `i_glob = i_own` (sender) /
   `M + i_own` (receiver) makes the parity alternation continue **across the
   region boundary**. Non-own cells are pure router pass-through on that pipe's
   two colors.
3. **Store-and-forward chain** (`decode_strip.csl`, 3-task async chain per role,
   looped `MAX_OUTPUT_LEN` times):
   - sender own_i: `recv` own B from block → `fwd` `i*B` upstream wavelets
     (own_0..own_{i-1}) → `inject` own B onto tx.
   - receiver own_j: `consume` own B → `post_fwd` `(M-1-j)*B` downstream →
     `broadcast` own B into the block on `intra_row_bcast_color` (6), q0 OQ.
   Net effect: sender `ly` → receiver `ly`, shard-preserving.
4. **Strip → block.** `route_calc` paints `is_inter_row_recv_block` so every
   block PE receives `intra_row_bcast_color` from `DIR_IN` and forwards to
   `DIR_OUT`, except the far edge which only ramps in.

**Color budget:** 16 layout-global ids, `_kpipe_ids` (`launch.py:610-613`) =
`(1,2),(3,4),(5,7),(8,9),(10,11),(12,13),(14,15),(16,17)`. Pipes 0–2 **alias the
collective colors 1–5**; pipe 3's ids (8, 9) are also HT_head's `DOWN_A/DOWN_B`.
Safe only because strips (fabric_x ≥ PLACE_X) and the HT band are X-disjoint —
asserted in comments, not in code.

**Queue rebinding on strips** (`decode.csl` `dispatch_init_task:1516-1522`):
`comm_pe` binds IQ3..IQ7 as masters for collective colors 1–5, which the K-pipe
reuses. Strip PEs first **park IQ3..IQ7 on `x_input_color`** (unrouted there) so
that rebinding IQ2 → `rx_color` cannot trip "two master input queues for the same
color". Then IQ2 = rx, OQ7 = tx. Sender additionally swaps q0/q1 when
`sender_edge_parity` is odd so q0 always carries the active inter color.

### Implications / next actions

- [ ] `e2e-topology-full.svg` is misleading on two counts: x131 is the decode
      **west strip**, not part of the west HT band; and x644 (the **east strip**,
      the only real one in 2×2) is absent. Redraw or annotate before this diagram
      is used for floorplan reasoning.
- [ ] The "K-pipe colors alias collectives 1–5 and HT_head's DOWN_A/B, safe
      because X-disjoint" invariant is comment-only. This is exactly the class of
      claim `csl-color-audit` would classify `ASSERTED`. Candidate for a check.

### Pointers

- `launch.py:203-226` (`strip_realness`), `:600-646` (`_kpipe_ids`, DOWN_A/B
  aliasing), `:1018-1040` (region width/placement, strip roles), `:1256`, `:1335`
  (fake-strip transit paint), `:2930-2945` (geometry / `total_w`).
- `src/decode/decode_strip.csl` (whole file), `src/decode/decode.csl:1465-1542`
  (`dispatch_init_task`), `src/decode/route_calc.csl:129-195` (INTER_A/B,
  `has_inter_send/recv`), `:443-452` (`intra_row_bcast` far-edge).
- `assets/prefill-decode-transfer/e2e-topology-full.svg` (the diagram in question).
