# KV farm t1: switch-forwarded Q chain on CS-3, and how spent SWITCH_ADV wavelets reach a data receiver — 2026-09-13

**Project:** wse3-performance-model
**Author:** claude (session 4b-layout-kv-stream)
**Status:** captured

## Situation

The KV farm's t1 Q chain (32 band PEs of one row each contributing a 16-bf16
piece toward the farm) was a CE store-and-forward chain: member j received the
j upstream pieces on IQ2 and re-sent them before its own. Replaced by the
router-level pattern of the shipped FFT transpose kernel: one colour, switch
pos0 = pass-through, pos1 = RAMP inject, `POP_ON_ADVANCE` + `RING_MODE`; the
originator sends piece + 1 × `SWITCH_ADV`, every other member piece + 2 ×
`SWITCH_ADV` (`ce_ignore` on all). The farm PEs downstream have no switch and
receive the whole stream with one fabin DSD.

## Findings

- **CS-3 (prefill 512 / decode 64, 6 positions/PE):** 1,241,770 → 1,177,712
  cycles per token (1.85× → 1.75× the 672,193 baseline), ≈ −1.8K cycles per
  layer execution; the CE chain was exposed block time, not overlapped work.
- **Delivery of spent control wavelets to a data receiver (device-confirmed):**
  the originator's 1-command wavelet, popped empty at the next PE, is
  enqueued at every downstream receiver as ONE 32-bit data wavelet (2 × 16-bit
  slots, data `0x8000`); the members' 2-command wavelets are not enqueued at
  all. Simulator (CTF `num_data` countdown) and silicon agree: a receive
  extent with +2 slots behind piece 0 ran 64 tokens × 36 layers clean; the
  same extent without them hung (900 s timeout); +2 per piece would have
  back-pressured and hung the clean run. Encoded as `q_pad0 = 2, q_pad = 0`
  in `kv_farm.csl`, skipped by a rebased memory DSD.
- **"Per layer" bookkeeping:** one token passes all four block rows (9 layers
  each) serially, so per-layer = per-token delta ÷ 36. An earlier ÷ 9 reading
  inflated every per-layer number 4× (corrected in the V3 README).
- **Device runs are timing-only:** farm K/V are zeros and `memcpy_required =
  False` leaves no seed/read-back path, so a Q-ordering error would be
  invisible on the device. Correctness rests on the simulator (KV-seed and
  top-k checks pass at every ladder step).
- Cost split after the switch t1 (CS-3 subtraction): ≈ 650 cycles per
  position per layer (t2), ≈ 62 per chain hop per layer (two-pass merge, 36
  hops ≈ 2.2K), ≈ 8K per layer position-independent (t2's short-vector
  `@map` issue overhead, m_head broadcast + rebinds, 520-wavelet hand-off +
  keeper tap, column flood, t8).

## Implications / next actions

- [ ] Context sweep (baseline vs farm, 2K/4K/8K prefill, decode 64) is the
      penalty curve — running as BASE_/FARM_{2K,4K,8K}.
- [ ] A device correctness harness for the farm (seeded K/V, host reference)
      before any capacity claim.
- [ ] Promote the delivery rule into `csl-switch-adv-pop-semantics`.

## Pointers

- `analyses/2026-09-13-kv-farm-v3-sim-integration/README.md` (results table,
  cost split), `docs/design/2026-09-02-kv-farm-s4-layout.md` §9.1 as-built
- `/home/lexu/build/4b-farm/s1/qwen3_4b-decode/src/{decode,kv_farm}.csl`
  (`farm_q_switch`, `q_pad0/q_pad`), `run_farm_cs3.sh` (FARM_SW/SW0/SW2)
- CS-3 logs `~/rsync/4b-farm-s1-logs/FARM_SW.log`
  (`wsjob-msfxixunj6iwszvxueapge`), `FARM_SW0.log` (`wsjob-zjrjfvjjc43jhgd223nkj5`)
- related: `2026-09-13-kv-farm-first-device-run-and-route-early-return-hang.md`
