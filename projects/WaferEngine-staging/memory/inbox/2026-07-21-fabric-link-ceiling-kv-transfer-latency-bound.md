# Raw fabric per-link BW vs the KV-transfer number — is 1.8 GB/s a fabric ceiling? — 2026-07-21

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured

## Situation this applies to

You measured the prefill→decode KV-cache transfer on real WSE-3 at ~1.8 GB/s
aggregate (L5 / full geometry) and need to know whether that is the fabric
topping out or the transfer algorithm leaving the wire idle — before deciding
whether it is worth optimizing.

## What happened / finding

- **One fabric link, clean single stream, measured on device = 3.91 GB/s**
  (plateau 3.900–3.909 flat from 30k to 900k wavelets; chunk=2000 also gave
  3.89, so the gap is NOT per-chunk loop overhead). That is **0.89× the disclosed
  ~4.4 GB/s/link spec** — real silicon sustains ~0.89 wavelet/cycle on a clean
  single-`@mov32` PE-to-PE stream; the residual is single-PE fabric-injection
  overhead, not the wire.
- Method that worked: **SdkLayout direct streams** (`memcpy_required=False`), two
  1×1 code regions joined by an on-device `layout.connect` (that connection *is*
  the measured link), host trigger-in/timing-out streams pinned to the
  appliance's known-valid **edge io_locs** (INPUT y=0 / OUTPUT y=1 at x=0). The
  memcpy-framework version failed on-appliance with *"All ingress tiles must be
  at the edge of the fabric"* — that was an io_loc placement bug, not a real
  limit. Source PE times start→ACK on its own TSC (single PE, no cross-PE sync).
- The WSE-3 **simulator gives exactly 4.39 GB/s (1.0 wavelet/cycle)** — an
  idealized wire model, so the sim number is tautological; only the device number
  is informative here.
- **Consequence for the KV transfer:** the ~1.8 GB/s aggregate is **2.2× below
  even one clean single link**, and ~0.1% of the seam's aggregate capacity. So the
  KV-transfer bottleneck is **latency / serialization** (multi-hop
  store-and-forward × n_ph planes run serially + host round-trips), **not a
  fabric ceiling.** Optimizing the movement algorithm (coalesce planes, bigger
  per-hop payload, cut-through, direct-route) is the lever, not the wire.

## Implications / next actions

- [ ] Fold the 3.91 GB/s single-link constant into topic
      `prefill-decode-transfer-bandwidth.md` as the reference ceiling for
      interpreting the A/B numbers.

## Pointers

- Microbenchmark: `/home/lexu/fabric_bw/` (`run_p2p.py`, `src/p2p_src_kernel.csl`,
  `src/p2p_dst_kernel.csl`, `launch_p2p_device.py`; README has method + verdict).
  Sim + device validated.
- Topic: `memory/topics/prefill-decode-transfer-bandwidth.md` (device ladder
  L0–L5, aggregate 1.803 GB/s at production geometry).
- Related skill: `cerebras-data-movement` (quoting BW numbers), and the
  SdkLayout multi-stream io_loc-pinning skill.
