# Micro KV farm 1-to-X ladder: the prefetch stays free through k = 8; the cost is the scan; k = 8 first hung on a fabin DSD stride property — 2026-10-03

**Project:** wse3-performance-model
**Author:** claude (session 4b-multicore-prefetch)
**Status:** captured

## Situation this applies to

You are feeding one compute PE from several storage PEs over one colour on
WSE-3 (KV farm, micro farm, any "k−1 storage rows per scorer" design) and
want to know whether the per-layer transport becomes a cost as the number of
senders grows, how to order several senders on one colour without a CE
handshake, and what breaks first.

## Measured (CS-3, prefill N / decode 64, cycles per token; record `analyses/2026-10-03-micro-kv-farm-group-ladder/`)

| context | k | D_k stream+discard | T_k full | E_k K-early | model T_k |
| --- | --- | --- | --- | --- | --- |
| 7,936 | 2 | 822,156 | 922,100 | 928,296 | 923,306 |
| 7,936 | 4 | 828,231 | 1,191,245 | 1,201,854 | 1,130,897 |
| 2,048 | 2 | 747,870 | 768,191 | 774,929 | 774,101 |
| 2,048 | 4 | 745,786 | 817,733 | 827,573 | 832,486 |
| 2,048 | 8 (staged landing) | 757,426 | 998,267 | 1,014,513 | 949,255 |

Baselines: shipped 8K 813,292; shipped compiled at the 2K geometry 742,543
(the shipped kernel's fingerprint and cycles change slightly with MAX_SEQ_LEN).
Fingerprints of T_k/E_k equal the shipped kernel at the same compile geometry;
T2_512/T4_512 equal shipped 512 (the only request sensitive to lost positions).

- Fetch exposed (D_k − shipped): +246 / +415 per layer at 8K, +148 / +90 /
  +413 (k = 2/4/8) at 2K — ≤ 2 % of a layer; seven slabs cost +413 of which
  ~0.35K is the k = 8 fix's staging copy. The fixed part is the window design's own-slab copy and receive
  bookkeeping, not transport.
- Scan (T_k − D_k): 87–105 cycles per position at 8K, i.e. the
  positions-per-PE model; T_k on the model line except k = 4 / 8K (+5.3 %,
  +1.7K/layer) and k = 8 / 2K (+5.2 %, +1.4K/layer): both appear once the
  remote window holds ≥ ~60 positions, neither is in D_k — memory-port
  contention of several landing streams with the scan over a large window is
  the open suspect; a 4K point for k = 4 would separate L- from k-dependence.
- Sending the K slab early (E_k) is 170–450 cycles per layer SLOWER (growing with k): the
  overlap window was not the limiter, and thick storage rows that are still
  members of the QKV Y reduce enter it later when they block earlier in a
  synchronous send.

## Mechanism that worked (simulator + device, k = 2 and 4)

Several senders on ONE colour ordered by router switch positions, no CE
handshake: bottom row RAMP→NORTH (originator, 1 SWITCH_ADV after each slab);
rows above host-painted SOUTH→NORTH (pos0) with pos1 RAMP→NORTH, POP_ON_ADVANCE
+ RING_MODE so each member's 2-command SWITCH_ADV pops itself back to pos0 and
advances the row above; compute row SOUTH→RAMP. Colour must be switch-capable
(ids {0–9, 12, 13, 16, 17, 20, 21}; id 10 is not). The spent originator ADV
lands as 2 data slots → every slab carries a uniform kv_cols trailer
(PAIR_GROUP_PAD0 / PAD knobs). Landing: position-interleaved window t = p·k + g
received by one mem4d DSD with a negative row stride, so the live slots are one
prefix and no masking op grows with k; valid L (kv_cols = 4) are those where
L and L+1 factor into ≤ 16 (10, 12, 32 fine; 16 not). All storage sends must
be synchronous: a second async op on a busy microthread is a simfab FAULT
("trying to save into ut_instr[0], but overwriting Instr"), not a queue.

## What broke, and the fix

- k = 8 image does not link at 8K (compute row: windows + score arrays over
  256 slots). At 2K the first attempt hung on the wafer and in simfab (option
  N too). ROOT CAUSE (simfab trace, notes §15.9): a 16-bit fabric-input mem4d
  receive whose compound middle stride is 8 consumes ONE element per wavelet
  (strides 2 and 4 consume two; |outer stride| up to 525 is fine), so the K
  receive swallows the V round and the V receive starves. Chain, control
  wavelets and collectives were all correct in the trace. FIX
  `PAIR_GROUP_KDSD = 3`: receive each round as one contiguous 1-D block (the
  device-proven SHARED receive) and scatter into the window with a
  memory-to-memory mem4d copy (~0.35K cycles per layer at L = 10). With it
  k = 8 reproduces the shipped kernel at the 2K geometry and at prefill 512.
  Rule: keep fabric-input DSDs 1-D or stride ≤ 4 for 16-bit data; reshape in
  memory.
- Run-script hygiene: a `case` label reused from an earlier round (T2_2K =
  TAIL2) ran the wrong config; the printed launcher params in the log caught
  it. Check job names against existing cases before adding a ladder.
- Appliance init failure "Node is under DiskPressure" is cluster-side; requeue.

## Answer

Up to seven storage rows per scorer the prefetch is free (≤ 0.45K/layer); the design's latency
is the scan the compute row pays alone (90 cycles/position). More rows dilute
compute exactly as the model says (plus ~5 % once the remote window is large,
open); what appeared at k = 8 was a DSD property, not a transport cost.

## Pointers

- `analyses/2026-10-03-micro-kv-farm-group-ladder/{README.md, ladder.csv, ladder.png, plot_ladder.py}`
- `demo/micro-kv-farm/code/group/IMPLEMENTATION-NOTES.md` §15; `logs/cs3/round10-group/RESULTS.md`; spec `CHANGE-MAP-zh.md` §10
- ContextBase log: https://context.ed-aisys.com/doc/2026-09-27-log-micro-kv-farm-1-in-2-paired-attn-rows-rung-1-on-cs-3-dsd-cost-model-next-steps-I2chiMZyfg (§14)
