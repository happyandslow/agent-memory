---
summary: Source-read reference for qwen3_1p7b-e2e token/KV dataflow, decode strips/K-pipe, HT_head/demux seams, and tensor layout findings.
tags: [waferengine-staging, qwen3, e2e, dataflow, topology, kpipe, ht-head]
---

# qwen3_1p7b-e2e Kernel Dataflow and Topology Notes

Source-reading session captured 2026-07-09 from `models/qwen3_1p7b-e2e`.
This note is the durable curated summary of `memory/inbox/2026-07-09-e2e-kernel-qa-log.md`.
Related: [[prefill-decode-transfer-bandwidth]], [[standalone-vs-integrated-kernel-parity]].

## Durable findings

### Prefill does not feed the sampled first token on-chip to decode

Only the **KV cache** crosses from prefill to decode on-chip. The sampled first token exits south from `pf_ht_tail` to host via `pf["logits_stream"]`; it is read/printed and is not sent back to the device. Decode step 0 instead uses a host-computed `host_x_f16 = W_E_full[cfg["token_ids"]]` seed (default token id 0), sent on `x_stream` into decode's demux. Therefore today's fused e2e run is fused in KV state only; it is not a true autoregressive continuation of the prefill-sampled token unless a host hop or new on-chip `pf_ht_tail → decode HT_head` token wire is added.

Decode HT_head feed colors:

| Wire | Color id | From → To | When |
|---|---:|---|---|
| `pre_embed_x_color` / `c1_color` | 18 | host → `x_demux` → HT_head west edge | step 0 only |
| `tok_bcast_color` | 7 | decode `ht_tail` root row → HT_head bottom edge | steps 1+ |
| `post_embed_x_color` / `c2_color` | 23 | HT_head diag PE → decode row 0 west | every step |
| `ht_ready_color` | 0 | HT_head col=0 → demux | init barrier |
| `UP_A/UP_B`, `DOWN_A/DOWN_B` | 21/22, 8/9 | HT_head internal W_E gather chains | steps 1+ |

KV cache path remains the known prefill gather/transform → north shift → decode ingress path on colors 17/21.

### Decode strip/K-pipe geometry is easy to misread

The demuxes are present in the topology diagram as dashed one-PE-wide regions, but the decode inter-row strip columns are not drawn clearly. For the real 512 config the decode row region spans x131…x644: x131 is the west strip, x132–643 are block columns, and x644 is the east strip. The shipped 2×2 config has only the **east** strip as a real K-pipe strip; the west strips are fake compile-time transit wires for step-0 X ingress and final Z egress.

The K-pipe is a corner turn for inter-row block hops. Intra-row hops ride `inter_block_a/b_color` directly across adjacent block columns; at the row tail the strip store-and-forward chain moves the shard-preserving Z payload south to the next row.

Color aliasing is forced by the 24-color WSE-3 budget. K-pipe uses 16 ids; most are also named by collectives or other regions. The safe invariant is stronger than the old "X-disjoint" comment: no wafer wire is driven by two users. The genuine overlap is at the queue-binding layer, handled by parking IQ3..IQ7 on `x_input_color` before binding IQ2 to the active K-pipe color on strip PEs.

**Latent hazard:** at `P_Y_BLOCK_NUM >= 4`, west strips become real and would need to carry K-pipe traffic as well as existing `result_color`/`post_embed_x` fake-strip transit assumptions. Taller-layout work must revisit this.

### HT_head/demux seams

`src/decode/demux.csl` is a one-shot store-and-forward scatter at fabric x=2. It takes the host's step-0 pre-embedded X seed, keeps one row shard per PE, and emits east on color 18. It waits for the HT_head ready barrier on color 0 so HT_head runtime-painted routes exist before the X wavelets arrive.

`src/decode/ht_head.csl` owns token embedding. At step 0 it drains the demux seed into `embed_buf`; from step 1 onward it receives token ids from HT_tail on color 7 and performs the W_E gather using northbound `UP_A/UP_B` and southbound `DOWN_A/DOWN_B` chains. The diag PEs emit the hidden shard east on color 23 into decode row 0, where row 0 fans X along the X axis.

`DOWN_A/DOWN_B` reuse K-pipe colors 8/9 purely for id scavenging. There is no semantic tie to the K-pipe; both users paint N/S-only wires in disjoint/adjacent regions, with no E/W boundary conflict.

### Data-layout reference artifacts

The delegated tensor-layout reference now lives under `assets/data-layout/`:

- `assets/data-layout/README.md`
- `assets/data-layout/e2e-data-layout-decode.md`
- `assets/data-layout/e2e-data-layout-prefill.md`

Headline: decode's axis roles ping-pong (`hidden Y → X → Y → X → Y`), while prefill is rotated 90° (`seq` on X, hidden dim on Y). This explains why the KV handoff transposes **V** but not **K**.

Verified source bugs/asymmetries from the layout read:

1. `src/decode/route_calc.csl:5` says sequence/KV-head bands are along X, but decode sequence is along **Y**.
2. Decode pads vocab 151936 → 152064 and masks 128 dummy logits; prefill does no padding and asserts exact divisibility.
3. `launch.py` P_BLOCK_SIZE comments describe a stale config (`P_BLOCK_SIZE=128, Pw=256`) rather than the shipped geometry.
4. `HT_X_OFFSET = 0` in shipped configs makes HT_head west relay-only columns dead code.
5. Prefill weights are all mock RNG weights; real HF weights need decode-side permutations/resharding equivalents.

## Next actions

- Decide whether fused e2e should carry prefill's sampled token into decode (host hop or on-chip wire) before making end-to-end accuracy claims.
- Redraw/annotate `e2e-topology-full.svg`: x131 is a decode west strip, and x644 (east strip, real in 2×2) must be visible.
- Add a color/topology check for K-pipe aliasing invariants and the `P_Y_BLOCK_NUM >= 4` west-strip hazard.
- Fix the stale `route_calc.csl:5` axis comment.
- Give `build_prefill` decode-like vocab padding or document that prefill requires exact vocab divisibility.
- Teach `tools/csl_color_audit/parse_csl.py` the raw `@set_config(addr/word_size, val)` form so e2e profiler code can be audited.

## Pointers

- `models/qwen3_1p7b-e2e/launch.py`: colors, placements, `strip_realness`, `_kpipe_ids`, HT_head/demux ports, relay build, host X seed.
- `src/decode/demux.csl`, `src/decode/ht_head.csl`, `src/decode/decode_strip.csl`, `src/decode/decode.csl`, `src/decode/route_calc.csl`.
- `src/prefill/prefill.csl` and `src/prefill/comm_pe.csl` for KV gather/transform/shift.
- New diagram artifact: `assets/decode-kpipe/kpipe-south.svg` (+ `.png`).

## Last updated

2026-07-11.
