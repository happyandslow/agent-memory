# prefill→decode transfer bandwidth — 2026-07-06

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured   <!-- captured | drained -->

## What happened / finding

- Started a tracking topic [[prefill-decode-transfer-bandwidth]] for the effective
  bandwidth of the on-chip KV handoff in `qwen3_1p7b-e2e`, with the explicit
  framing (Le's ask) that timing must count **both** the seam wire transfer **and**
  the on-PE transform/compute (gather + transpose + re-layout), not wire alone.
- Session was a source read of `models/qwen3_1p7b-e2e/`: mapped the handoff into
  3 timed segments — A prefill gather+transform (`kv_step` states 0–3), B north
  shift through the `Pw×2` relay seam (`kv_north_shift`), C decode receive+cache
  write (`kv_ingress`). Two transposes/re-layouts bracket one passive wire shift,
  so the transfer is compute-dominated, not memcpy.
- Confirmed the layout: decode (north) / relay seam / prefill (south) all share
  block columns via `PLACE_X = HT_WIDTH_tail + 4`; both `build_decode` and
  `build_prefill` compute PLACE_X by different arithmetic to the same value, which
  is what makes segment B a straight north shift.
- Built a floorplan visualization (Claude artifact) and saved it into agent-memory
  as the setup viz (html + pdf). It is static geometry only — carries no timing.

## Implications / next actions

- [ ] Instrument A/B/C with on-device TSC (+ host-wall cross-check) to get the
      first effective-GB/s number; see the topic note's measurement window.
- [ ] Fill the byte-total TODO for the 2×2 configs (bsz / kv_dim_per_pe /
      seq_len_per_pe / max_layers_per_block resolved from a run printout).
- [ ] Compare on-chip seam path vs pdSeparate host-DRAM bridge under the same
      both-segments-counted metric.

## Pointers

- Topic: `memory/topics/prefill-decode-transfer-bandwidth.md`
- Setup viz: `assets/prefill-decode-transfer/e2e-floorplan.{html,pdf}`
- Repo: `models/qwen3_1p7b-e2e/src/{prefill,decode}/…`, `src/relay.csl`, `launch.py`
- Related: [[kv-cache-policy-tradeoffs]], [[e2e-pdSeparate-device-validation]]
