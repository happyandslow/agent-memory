# Tall X+Z pipelines only 1 token at a time; A2 is a context-linear bottleneck that caps the overlap speedup — 2026-09-17

**Project:** wse3-performance-model
**Author:** claude
**Status:** captured

## Situation this applies to

You want the tall layout C decoder (A1 128×80 QKV / A2 128×256 attn+O / A3
128×160 FFN, router "staircase" reshards, `demo/fused-block/xz-staircase/`) to
run as a *fine-grained pipeline* — the three physical stages overlapping so
throughput approaches one token per max-stage instead of per-layer. You measured
feedback multi-layer at W=2 giving only 1.47× (not ~2×) and want to know why, how
many buffer slots a fix needs, and whether it's worth it at long context.

## Findings

**1. The feedback ring is serial by construction — one token in the loop.**
`group_link.csl` (A3→A1 feedback) + the A1 admission gate `tall_stage.csl:338`
(`if tick<frames and (!feedback or tick%layer_banks==0)`) let A1 admit the next
token only after the current token's *last* layer; each intermediate layer waits
a full A1→A2→A3→A1 round trip during which A1 idles. Single-buffered in two
places: one `kernel.ptr_X` is both the token-entry buffer (`tall_stage.csl:315`)
and the group_link feedback landing (`link.init(...,kernel.ptr_X)` line 303,
arm at `group_link.csl:70-71`); one outstanding arm (`@block(di)` 66, re-arm only
after consume 73-76). So W>1 STARTs pile up unread — the bubble is structural,
not a scheduling knob.

**2. The forced-decode kernel already solved the multi-in-flight *state*, but
tall doesn't engage it.** `decode.csl` `attn_step_pair` (1985-2025, `forced_mode`)
keeps two in-flight tokens: `X_hold[2]` (594) residual holds, `freqs_hold[2]`
(596-597) RoPE snapshots, per-layer `iter_num_bank`/`step_bank` (740-741, lockstep
consecutive positions). `rope_step_advance` (the real recompute) is **per-token**,
2× up front; every A1 trigger only *restores* a snapshot by memcpy (2006-2007), not
recompute. tall's `a1_layer_body` path uses a single `freqs_cos/sin` + single
`ptr_X` and never sets `forced_mode` → tall runs serial. **PR #16 "Pipeline
parallel" in WaferEngine (drafter/qwen3-drafter-decode) is a *different* answer**:
8 physical stages, forward-only micro-batch pipeline, per-`[slot×layer]` banks —
it avoids the loopback ring by spending area, not by fixing group_link.

**3. Slot analysis for a single-request forced pipeline (decision):**
- RoPE hold = **structural, N = S = 3** (Little's law: 3× fill ⇒ 3 tokens in
  ring, all distinct positions since a token can't occupy two ring stages at
  once). Perfect stage-balance does NOT reduce it. Cheapest impl: **1 base
  snapshot + pointer-swap the `freqs_cos_dsd/sin_dsd` base + 1-base incremental
  recompute** (Le's idea — no memcpy to a working buffer, ~0 new SRAM).
- residual landing + group_link in-flight = **elastic, ≤ S-1 = 2** (bubble
  byproduct: 1 if stages perfectly aligned, up to S-1 when one stage dominates;
  capped at S-1 — more imbalance idles A1/A3, doesn't need more slots). Reuse
  forced's `X_hold[2]` → 0 new SRAM.
- iter_num/step = reuse existing `iter_num_bank[layers]`, 0 new.
- Net new SRAM ≈ 0. Multi-*request* slots (drafter's) are NOT needed for forced
  single-request; layers separate state along the anti-diagonal, positions along
  the ring.

**4. Per-stage compute vs context (CS-3, tall single-layer `--prof`, seg-tsc
median over steps 4+, two probe PEs averaged; cyc/token):**

| context | A1 QKV | A2 attn | A3 FFN | serial TIMING | A1:A2:A3 |
|---|---|---|---|---|---|
| 1280  | 4,909 | 7,746  | 7,536 | 28,422 | 0.63:1:0.97 |
| 2560  | 4,930 | 8,523  | 7,536 | 29,204 | 0.58:1:0.88 |
| 5120  | 4,895 | 9,578  | 7,541 | 30,243 | 0.51:1:0.79 |
| 15360 | 4,896 | 13,957 | 7,540 | 34,620 | 0.35:1:0.54 |

- **A2 (attention) is the sole bottleneck and grows linearly** ≈ 7,100 + 0.44·ctx
  (score length ∝ position). **A1 ≈ 4,900 and A3 ≈ 7,540 are flat** in context.
- **The overlap speedup DECAYS with context** (Amdahl on the max stage):
  serial/A2 ≈ 3.7× @1280 → 3.2× @5120 → **2.5× @15360**. Fine-grained pipeline
  is worth most at short/medium context; at long context A2 *is* the layer and
  must itself be split/optimized — overlapping A1/A3 around it buys less.

## Constraints / gotchas surfaced

- **prefill must be a multiple of 1280** (= LCM of the three stage heights
  80/256/160; `@comptime_assert(prefill % height == 0)` `tall_stage.csl:416`
  compiled per stage). prefill=16128 fails; 15360 (=12·1280) is the largest ≤16K
  multiple. Cost me one job.
- **2× KV cache fits at 1 layer:** `capacity=8192→16384` (kv_len_per_pe 32→64)
  **compiled and ran** at 15,360 context. `[unverified]` for multi-layer feedback
  (KV × layers) — check before assuming 16K fits with layer_banks≥2.
- Added a `--capacity` passthrough (`run_case.py`, `launch_tall.py:205`, default
  8192, behavior-preserving) since capacity was hardcoded.
- A local backgrounded ssh to CS-3 was **killed for host low-memory**; the remote
  `device.py` (not setsid) **survived** and the wsjob completed — verified by
  `ps`/`csctl`/result file, not assumed. (Restated: a local kill ≠ remote failure.)

## Implications / next actions

- The fix is harness/group_link surgery (double-buffer feedback: per-slot residual
  + RoPE pointer槽 + admission decoupled from `group_ready`), NOT new buffers/banks
  — reuse `X_hold[2]`, pointer-swap RoPE. Crosscheck: don't modify shared serial
  fns (`rope_step_advance`/`set_attn_layer`/`iter_num_bank`), only add tall-side
  holds, so forced's oracle stays byte-identical.
- [ ] per-stage timing at long context for feedback (multi-layer) — the numbers
  above are single-layer; KV×layers SRAM and A2 growth need the feedback build.
- Deployment target: 8 physical copies × 3 substages = 24 stages, ideal 24× over
  fully-serial; the within-block ×3 is what group_link currently blocks.

## Pointers

- `demo/fused-block/xz-staircase/package/tall/src/{tall_stage,group_link,decode}.csl`
- CS-3 segs: `~/rsync/xzstair-cs3-rsync/package-xz/prof-p{1280,2560,5120,15360}/segs_parsed.json`
- Diagrams: `docs/diagrams/2026-09-14-layoutC-a2-sync-timesteps.png` (reshard
  timesteps), `2026-09-10-layoutC-full-allocation.svg` /
  `2026-09-10-layoutC-tall-a2.svg` (layout)
- Related: [[qwen3-4b-cs3-measurements]] (per-slot cycles), the 3.7×→one-barrier
  finding `inbox/2026-09-14-layoutc-3p7x-is-one-sync-barrier-not-compute.md`
- WaferEngine PR #16 `6708757` (drafter micro-batch pipeline — the area-spending
  alternative)
