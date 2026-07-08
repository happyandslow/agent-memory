# h2d-playground full review — 2026-07-08

**Project:** WaferEngine-staging
**Author:** claude
**Status:** drained   <!-- captured | drained -->

## What happened / finding

- Read the whole `h2d-playground/` tree on branch `lexu/h2d-explore` (~767 files,
  22 experiment dirs, 2026-05-05 → 2026-06-09, mostly real WSE-3 on EPCC CS-3)
  and curated it into the new topic note [[h2d-host-device-bandwidth]].
- This is the **host↔device / host↔host** transport story, distinct from
  [[prefill-decode-transfer-bandwidth]] (the on-chip prefill→decode KV handoff).
- Four headline conclusions, all backed by sweeps re-derived from the raw logs
  rather than taken from the READMEs:
  1. **Auto-picked `io_loc` caps S=16 SdkLayout streams at a hard ~4.2 GB/s
     plateau independent of payload size.** Pinning unlocks 11–15 GB/s (TSC).
     Verified across the full `bw_parallel.{H2D,D2H}_v3.{pin,nopin}.S16.K*` log set.
  2. **Several headline numbers in `h2d_playground_overview.md` are measurement
     artifacts.** The "54.6 GB/s D2H" is a `loop_count=5` reading; the same
     config at `loop=500` gives **4.77 GB/s**. The author's own
     `h2d_playground_overview_caveats.png` suspected this — the loop sweep
     confirms it and turns the hypothesis into a measured fact.
  3. **memcpy is linear in payload, SdkLayout direct-stream is flat.**
     `e10`: memcpy `RTT = 0.025·T + 0.76 ms`, sdklayout `RTT = 0.0002·T + 0.63 ms`.
     Per-pipeline-stage marginal cost 12.98 ms vs 0.33 ms.
  4. **On CS-3 the network, not the wafer, is usually the bottleneck**, and the
     three biggest losses are one-line fixes: wrong NIC (8×), `ROW_MAJOR`
     memcpy order (5×), missing `--h2d-sub-batch-wavelets` (~50×).
- Corroborated a `cerebras-debugging` claim first-hand: `InconsistentVersion`
  (client 1.14.0 vs server 1.13.2), `Could not find coordinator IP:port`, and
  `Empty ingress service url` all appear verbatim in **successful** `e5` runs.
  Benign preamble, confirmed.
- `e16` is CONCLUDED and worth not re-chasing: controller↔worker TCP is dead,
  UDP is one-way (controller→worker only, gateway SNATs to `10.24.x`), and the
  controller VM has no `/dev/infiniband` so RoCE controller↔worker is impossible.
  The 2.4 ms `launcher.run()` gRPC round trip is the hard floor.
- `rdma-explore` never produced a number: the worker pod has working verbs and
  HCAs but no `perftest`, no UCX, and **no libibverbs headers**. The "10× BW,
  1000× lower latency" figure circulating in the READMEs is an *expectation*.

## Implications / next actions

- [ ] Fix or annotate `h2d_playground_overview.md` — it publishes the 54.6 GB/s
      D2H artifact as a result. Anyone reading only that table gets a wrong
      mental model of D2H capability.
- [ ] Disambiguate the `ch16 m512×n512` H2D number: overview + caveats say
      7.38 GB/s, `bandwidth-test/logs/` says 9.20 GB/s at `loop=5`.
- [ ] Investigate the `K=32768` regression in `bandwidth-test-parallel`
      (pinned H2D 11.43 → 7.83 GB/s; host-wall 578 ms → 2119 ms for 2× data).
      Suspect host memory pressure, not fabric.
- [ ] If `e7`'s absolute `device_ms` is ever load-bearing, re-derive at 1.1 GHz
      (it used 850 MHz; see `cerebras-sdk-pe-timestamp-timing`).

## Artifacts produced this session

- Topic note: `memory/topics/h2d-host-device-bandwidth.md`
- New skill: `~/.claude/skills/cerebras-data-movement/` — the judgment layer for
  bandwidth/latency/transport work on CS-3, routing to the seven existing
  granular bandwidth skills. Sibling to `cerebras-debugging`.
