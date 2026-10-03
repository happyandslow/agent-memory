# The SD device run finishes clean but the latency split has holes: no device rows, an empty appliance stage, or an appliance p50 of ~3 s — 2026-10-03

**Project:** nc_service
**Author:** claude
**Status:** captured

Retroactive capture from the 2026-07-28/29 M2 overnight session (the W5 timing-map
investigation and W3b's timing plumbing). The headline numbers of that night are in
[[2026-07-29-m2-device-bringup-and-the-ingress-blocker]]; this note records only the
instrumentation gotchas that note does not, re-verified against the current tree on
2026-10-03 (`gateway_frontend.py`, `sd_kernel/device_timing.py`,
`utils/stage_join.py`, `utils/latency_report.py`).

## The situation this applies to

You drove the sd-pdSeparate kernel through the bridge (or a new driver that
reuses `gateway_frontend.run_session`), the run completed with
`verifier failures == []`, and now one of these is true of the report:

- there are **zero device TSC rows**, so the "device" column is blank;
- the **appliance stage is empty** even though the worker ring file is full;
- the appliance stage is present but its p50 is **~3 s**, i.e. `block_ms`;
- `python_timings` / per-stage Python rows are **empty** although
  `IOP_SPECDEC_TIMING=1` was exported.

Each of these is a wiring gap, not a measurement. They all look like "the kernel
emitted nothing", which is the dangerous part.

## What happened / finding

- **The decode kernel measures itself and then discards it.** `receive_batch`
  drains an 8-word TSC burst per batch into a local list, but the verdict keeps
  only `batch_count`; the `tsc["per_round"]` key that `launch.py` reads is only
  written by the *prefill* path. On the decode path there is no device number
  unless something intercepts. `device_timing.install_tsc_sniffer` does that by
  rebinding `launch_decode._serve_loop` to hand the real loop a proxy runtime
  (same idiom as `bridge_target`). It must be installed on the **same module
  object** the serve thread imports, **before** the serve thread starts, and
  `handlers.py` enforces that order. A no-op patch is silent — a run with no
  device rows is indistinguishable from the kernel emitting none — so
  `test_device_timing` pins both halves against the vendored source.
- **The sniffer keys on call shape, not stream identity**: a uint32 receive of
  exactly 8 elements. That collides when a draft record is itself 8 words, which
  `kernel_env.record_words(top_k)` yields at **top_k == 3**. Shipped configs use
  top_k = 20 (34 words), but the sniffer refuses to install at the colliding width
  rather than trust that. If a future config uses top_k = 3, expect a loud
  bring-up failure, not microseconds.
- **Clock constant**: this family converts at **0.85 GHz**
  (`launch_prefill.py` does `span_cycles / 0.85e9`). The sibling
  `qwen3_1p7b-{prefill,decode}` launchers divide by 1.1e9 — different kernels, do
  not copy that constant across.
- **Two ring-row dialects.** The in-process patch handler's ring rows carry
  `appliance_ns`; every consumer that computes the appliance stage
  (`driver_main`, `latency_report.py`, `stage_join.py`) reads
  `reply_ns - recv_ns` and **skips rows lacking those keys**. A ring written in the
  `appliance_ns`-only dialect yields a silently empty appliance stage. The sd ring
  rows now carry both; keep it that way when adding a new row writer, and keep
  device rows tagged `kind="device_tsc"` so the ring readers skip them.
- **`appliance_ns` includes the long-poll wait.** A PENDING exchange is
  ~`block_ms` of pure waiting counted as appliance time. Percentiles over the raw
  ring are therefore ~3 s at p50. Join ring rows to exchange rows **by seq** and
  drop PENDING seqs before percentiling (`stage_join.py` does this; the driver
  summary also reports the PENDING set it derived versus the one `SdSession`
  recorded — a mismatch there is a bug, not noise).
- **`IOP_SPECDEC_TIMING` is read once at import** (`_MB_TIMING` at module
  level in `gateway_frontend.py`), and it only gates the per-round RTT print. It
  does **not** produce `python_timings`: that is a caller-supplied list argument
  to `run_session`, filled by mutation, never written anywhere. A driver that
  wants per-stage Python rows must allocate the list and pass it
  (`sd_device_check.py` and `sd_service.py` do). Setting the env var after
  import, or expecting it to populate stage rows, gives nothing.
- **leg-1 wire time is only visible at the mock verifier** (`svc.rtts_ms` in
  `mock_verify_host`); the gateway's `rtts` bracket pump exchange + response
  build, not the gRPC receive wait. And with the verifier on loopback it is a
  lower bound on a real GPU host.

## Implications / next actions

- [ ] Any new driver on this path: pass a `python_timings` list, call
      `fetch_timing()` **before** `close()`, join by seq and drop PENDING before
      percentiling, and assert device rows > 0 as a hard check (not a warning).
- [ ] If the record width ever becomes 8 (top_k = 3), the sniffer will refuse —
      switch the discriminator to stream identity before chasing the error.

## Pointers

- `waferengine/samples/specdec/sd_kernel/device_timing.py` (module docstring is
  the authoritative explanation), `sd_kernel/handlers.py` (install order),
  `sd_kernel/tests/test_device_timing.py`.
- `waferengine/samples/specdec/gateway_frontend.py` (`_MB_TIMING`,
  `python_timings`), `waferengine/utils/{stage_join,latency_report}.py`.
- Session narrative: `M2_NIGHT_LOG_2026-07-28.md` at the work-repo root (W5/W3b).
- Related: [[2026-07-29-m2-device-bringup-and-the-ingress-blocker]],
  [[2026-07-28-m2-s1s2-staging-and-real-cfg]],
  [[2026-07-27-why-patch-the-target-not-the-launcher]].
