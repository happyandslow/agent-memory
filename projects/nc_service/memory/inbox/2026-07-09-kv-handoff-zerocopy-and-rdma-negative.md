# KV-handoff zero-copy serde fix + RDMA negative result — 2026-07-09

**Project:** nc_service
**Author:** claude
**Status:** drained

## What happened / finding

- **Zero-copy KV handoff seam (nc_service `23ab43a`) — DEVICE-CONFIRMED.** The decode
  handler did `np.frombuffer(raw[:kv_nbytes], u32).tolist()` (materializing the 128 MB KV
  as ~33M python ints, ~0.43 s) and `_unframe_blob` then rebuilt an array with
  `np.asarray(list)` (~0.61 s): ~1.0 s of pure array→list→array round-trip **per request,
  on every transport**. Fix: hand the appliance a uint32 **view** —
  `np.frombuffer(memoryview(raw)[:kv_nbytes], dtype=np.uint32)`. `memoryview` slicing clamps
  exactly like the old bytes slice with no copy; `np.asarray` on a uint32 ndarray is a free
  no-op. Same fix in `pd_worker.py`; mock `DecodeAppliance.load_kv` passes it straight to
  `ApplianceSession.send` (already `np.asarray(...).copy()`). Also fixed `_unframe_blob`'s
  double copy (`.tobytes()[:n_bytes]` copied padded `n_words*4` then trimmed → one copy).
- Device (jids `2d36yuh`+`93vcqps`, rc=0, 43 rounds, same `run_kvt2.sh` TCP baseline):
  decode `unframe` **789.9 → 23.0 ms** (34×); decode `load_kv` total **900.3 → 137.3 ms**;
  `r=1` KV-ingest round **1539.8 → 239.3 ms**; full run **4494.3 → 3136.7 ms**; qps **9.6 → 13.7**.
  No regression: `r=0` 2163.9 ms (prefill-side untouched), wire 82.9 ms, rewind n=41
  mean 17.89 ms (was 18.17). Byte-identical; `test_kv_handoff_zerocopy.py` pins ndarray-vs-list
  equality (clamping, read-only views, bad-magic). SDK-free suite 201 pass / 2 skip.
- **RDMA: a useful NEGATIVE result.** RDMA now genuinely works pod-to-pod (`dc60b4e`) after
  two fixes: (1) `e8f8feb` — `controller.py` seeded the worker env from the original `/proc`
  env and forwarded `IOP_*` only `if _key not in env`, so a stale value shadowed the run's
  `IOP_KV_BACKEND=rdma`; the controller env is the current run config and must win. Also log
  the **resolved** backend on both ends so a silent tcp fallback can never again be mistaken
  for an rdma measurement. (2) `dc60b4e` — our `rdma_backend` defaulted to device `rxe0`
  (soft-RoCE, absent) + hardcoded `gid_idx=1`. Per the h2d-explore `rdma-explore` example the
  pods have real HCAs **`mlx5_0`/`mlx5_1`**, and GID 0/1 is link-local IPv6 (RoCE v1) that does
  **not** route between pods — you need the RoCE v2 IPv4 GID. Ported `dump_gid_table`/
  `auto_gid_idx` (pure `/sys` parse, no verbs/root); defaulted `IOP_RDMA_GID_IDX=auto`.
- **And RDMA does not help:** with both ends `resolved=rdma` and 128 MB crossing over RDMA,
  `r=0` handoff = **2283 ms (rdma) ≈ 2196 ms (tcp)**. The wire was ~70–82 ms of a ~2.2 s
  handoff all along. Swapping the transport end-to-end and watching `r=0` not budge is the
  empirical proof the cost was host-side — which is what pointed at the serde.
- Correction worth keeping: the h2d-explore curation states **RDMA-Write was never benchmarked
  on EPCC** (no perftest/UCX/libibverbs headers); the circulating "8–11 GB/s, 1–3 µs" and the
  older "warm RDMA 45→5 ms validated" note are **expectations, not measurements**.
- Also earlier this cycle: `44b4379` vectorized `kv_transform.transform()` (7-deep python
  scatter loop) — 15.3 s → 336 ms on device, byte-identical. Combined, the one-time KV handoff
  went **~18.7 s → ~2.5 s**.

## Implications / next actions

- [ ] **New bottleneck = prefill `egress` 1520 ms.** Instrument it before optimizing: it is a
      host `perf_counter` bracket around the whole blocking `PrefillApplianceReal.prefill()`
      (send prompt → wait for the wafer's prefill forward → read 128 MB KV back), i.e.
      **compute + D2H lumped, not isolated D2H**. Needs on-wafer TSC-at-emit vs host-recv to split.
- [ ] Optional next lever: the handoff blob is an **npz** (`np.savez` / `np.load(io.BytesIO)`) —
      `encode` 169 ms + `handoff` 80 ms + the residual 23 ms `tobytes`. A raw header + two
      contiguous arrays would reclaim most of ~270 ms (wire-format change, both ends).
- [ ] `e8f8feb` touches the generic backbone (`io_pipeline/controller.py`) — flag it in PR review.
- [ ] Remaining measurement hygiene: `rdma_backend` emits no `[KV_TIMING wire]` line, so RDMA has
      no isolated wire number; clear `_runs/kvt_rdma/kvt_*.txt` between runs (stale TCP lines
      once misled a read).

## Pointers

- nc_service branch `lexu/specdec-real-kernels`: `23ab43a` (zero-copy serde), `dc60b4e` (RDMA
  auto-GID), `e8f8feb` (controller env authority + resolved-backend log), `44b4379` (transform).
- Topic note: `memory/topics/specdec-modeb-drive-path.md` (drive path, timelines, measurement
  boundaries, RDMA + serde resolutions).
- Raw data: nc_service `_runs/kvt_saved/kv_timing_2026-07-08.txt`.
- Timelines: `../artifacts/2026-07-08-specdec-round-timelines.png` (+ `.html`).
- RDMA recipe source: `happyandslow/WaferEngine @ lexu/h2d-explore`,
  `h2d-playground/rdma-explore/` (`dispatch_rdma_bench.py --device mlx5_0 --gid-idx auto`,
  `probe_pingpong.py:auto_gid_idx`); curated in WaferEngine-staging topic
  `h2d-host-device-bandwidth`.
- ContextBase log (this session): `m62qbYvGQv` —
  https://context.ed-aisys.com/doc/2026-07-09-kv-handoff-zero-copy-serde-unframe-790ms-to-23ms-rdma-works-but-does-not-help-m62qbYvGQv
- ContextBase log (2026-07-08 predecessor): `cKDd6Y66yG` under PD Disaggregation (living).
