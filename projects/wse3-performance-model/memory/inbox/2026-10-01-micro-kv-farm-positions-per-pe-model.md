# Decode attention cost depends only on positions per compute PE: the 1-in-k pair model, measured on CS-3 — 2026-10-01

**Project:** wse3-performance-model
**Author:** claude (session 4b-multicore-prefetch)
**Status:** captured

## Situation this applies to

You are pricing any design that moves KV off the PE that scores it (pairing,
micro farm, storage rows, remote fetch) on the shipped Qwen3-4B decode block,
or you need the decode cycles for an arbitrary context on this kernel, or you
are deciding how many storage PEs to hang off one compute PE.

## Measured (CS-3, prefill N / decode 64, cycles per token; record in `analyses/2026-10-01-micro-kv-farm-sweep/`)

| context | L shipped / pair | shipped | TAIL1 (pair, stream lands in cache tail) | TAIL2 (control, same geometry, positions counted local) |
| --- | --- | --- | --- | --- |
| 512 | 2 / 4 | 672,961 | 727,939 | 724,107 |
| 2,048 | 8 / 16 | 742,373 | 766,633 | 763,756 |
| 4,096 | 16 / 32 | 769,923 | 820,943 | 817,758 |
| 7,936 | 31 / 62 | 813,292 | 916,953 | 913,250 |
| 16,128 | 63 / — | 920,527 | does not link (landing zone allocated per layer) | — |

TAIL1 reproduces the shipped top-20 index hash at every context.

## The model

With L = positions held (scored) per compute PE = k × context / 256 (k = 1
shipped, 2 for the 1-in-2 pair), every variant lies on one line for L ≥ 4:

    cycles per layer ≈ 19,881 + 90.1 × L      (× 36 layers per token; residuals ≤ 85)

- Same-L configurations agree to < 1 % (shipped 16K vs pair 8K; shipped 4K vs
  pair 2K). A streamed position costs what a local one costs; the role split
  has no measurable fixed cost (TAIL1 − TAIL2 ≈ 100 cycles/layer). Moving
  K/V every layer is free; the positions are not.
- The shipped kernel at 512 context (L = 2) is 1.35K/layer BELOW the line —
  an anomaly of the shipped kernel at tiny L, not a pair cost (an earlier
  "+1.4K/layer fixed role-split cost" was this).
- Predicted penalty of a 1-in-k design with all positions scored on the
  compute PE: penalty(C, k) = 90.1 (k − 1) s / (19,881 + 90.1 s), s = C/256.
  k = 2: +4 % (2K), +13 % (8K; measured +12.7 %), +23 % (16K), +34 % (28K);
  k = 4: +11 / +38 / +68 / +101 %. k > 2 is unmeasured (assumes transport stays
  free as more slabs stream in).
- The lever for the capacity/latency exchange rate is the 90 cycles per
  position (score passes, band all-reduce payload, exp, per-position P·V op).

## Why the pair variants differ (history, all measured)

Rung 1 (separate K_r/V_r buffers, second set of short DSD ops per stage):
+11.5 % at 512, +27.5 % at 8K. Option P (storage rows pass-through for the
softmax Y reduces): −40 cycles/layer, null — the shipped chain hop is already
streamed. Subtraction profile: transport free; all excess was the second block
of ops. Cache-tail landing (one op per stage): +8.2 % / +12.7 %.

## Capacity consequence (decision 2026-10-01)

The cache-tail version allocates the landing zone inside every layer's cache
slab (contiguity with the per-layer local prefix), so the compute image grows
like an all-local kernel and 16K no longer links. Next design: the compute row
holds **no local KV** — one landing buffer shared by all layers, every position
on the storage row(s), the storage row appends every step (all rows project K/V
redundantly, so no forwarding), prefill rows forwarded once at boot. SRAM per
position on the compute row drops from 144 B (9-layer local) to 40 B (score
24 + landing 16); timing is the same model at L = (k − 1) C / 256.

## Pointers

- Figure `analyses/2026-10-01-micro-kv-farm-sweep/sweep.png`, data `sweep.csv`, script `plot_sweep.py`.
- Design/notes: `demo/micro-kv-farm/CHANGE-MAP-zh.md`, `code/pair/IMPLEMENTATION-NOTES.md` §6–§11; diagram `docs/diagrams/2026-09-30-micro-kv-farm-cache-tail.png`.
- ContextBase: https://context.ed-aisys.com/doc/2026-09-27-log-micro-kv-farm-1-in-2-paired-attn-rows-rung-1-on-cs-3-dsd-cost-model-next-steps-I2chiMZyfg
