# PD Disaggregation — M-par (parallel-stream TCP KV backend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use `- [ ]` checkboxes.

**Goal:** Make the `kv_channel` TCP backend move a KV blob over **N parallel streams** (default 16, configurable), superseding the single-stream implementation, so it can saturate the 100 GbE link (~12.3 GB/s per e17's "tcp-16") and serve as the honest non-RDMA A/B baseline against `backend="rdma"` on CS-3.

**Architecture:** `backend="tcp"` becomes a parallel-streams transport ported from the proven `rdma-explore/tcp_pump.py` S-stream model: the sender splits the KV buffer into `N` contiguous chunks (remainder front-loaded) and sends each on its own socket/thread to the receiver's single published address; each connection carries a small header `{rid, n_streams, stream_idx, total_len, offset, chunk_len}` + its chunk; the receiver reassembles by offset and delivers keyed by `request_id` once all `N` chunks for that `rid` arrive. `N` comes from `IOP_KV_STREAMS` / a `streams=` param (default 16); **`N=1` is the single-stream floor** (a config, no longer a separate default). Rendezvous is unchanged (one published address; the sender opens `N` connections to it). `backend="rdma"` is untouched.

**Tech Stack:** Python 3 stdlib (socket/struct/threading), `kv_channel` (M1/M3), pytest. Port source: `WaferEngine` branch `lexu/h2d-explore`, `h2d-playground/rdma-explore/tcp_pump.py` (the `_split` + per-stream `sendall`/`recv_into` model; the e17 RDMA A/B reference).

## Global Constraints

- **`.proto` UNCHANGED**; **KV disk-free** (host RAM only); **decode egress batched** — all unchanged.
- **`backend="tcp"` default is now N=16 parallel streams**, `N` from `IOP_KV_STREAMS` (env) or a `streams=` kwarg; explicit kwarg wins over env; `N=1` = single-stream. `N>=1` required (`ValueError` otherwise).
- **Both ends must agree on the framing** — the receiver reads `n_streams` from each connection's header and waits for exactly that many chunks for a `rid`, so a sender using `N` and a receiver are consistent without the receiver being pre-told `N`.
- **Correctness is stream-count-independent:** for any `N`, `send(rid, buf)` then `recv(rid)` returns `buf` exactly. Tiny buffers use `effective_N = min(N, len(buf))` (>=1) so there are no zero-byte streams; `effective_N` rides in the header.
- **Public API preserved:** `KvReceiver(bind=..., *, backend="tcp", streams=None)`, `.address`, `.recv(request_id, timeout)`, `.close()`; `KvSender(peer, *, backend="tcp", streams=None)`, `.send(request_id, buf)`; `introduce(...)`. Existing callers (M2 handlers, M2a `pd_worker`) need no change and get N=16 by default on both ends.
- **The M1 close-leak guarantee holds:** `close()` still joins the single accept thread (`_t`), no leaked threads/ports.
- **`rdma` backend untouched.** Backend selection (`_resolve_backend`) unchanged except threading `streams` through.
- Run host tests from repo root: `python3 -m pytest waferengine/samples/specdec/tests/ -q`.

---

### Task 1: N-stream TCP transport (supersede single-stream)

**Files:**
- Modify: `waferengine/samples/specdec/kv_channel.py`
- Test: `waferengine/samples/specdec/tests/test_kv_channel_parallel.py` (new)

**Interfaces:**
- Consumes: nothing new (stdlib).
- Produces:
  - `_TcpTransport(bind, *, streams)` — receiver side: one listening socket + accept thread; per-connection reads the chunk header + chunk, buffers `{rid: {offset: chunk}}` with a per-rid expected-count, assembles + delivers via the condition var when all `effective_N` chunks arrive.
  - Sender: `_TcpTransport.send(peer, request_id, buf, *, streams)` — split into `effective_N = min(streams, max(1, len(buf)))` contiguous chunks (front-loaded remainder), open `effective_N` connections concurrently, one thread each, sending `header + chunk`; join all; raise on any stream error.
  - `_resolve_streams(explicit)` — `explicit` kwarg else `int(os.environ.get("IOP_KV_STREAMS", "16"))`; `ValueError` if `< 1`.
  - Chunk header wire form (little-endian): `<rid_len:u32><rid><n_streams:u32><stream_idx:u32><total_len:u64><offset:u64><chunk_len:u64><chunk>`.
  - `KvReceiver`/`KvSender` gain `streams=None` (keyword-only); resolved once in `__init__`.

- [ ] **Step 1: Write the failing tests** — `tests/test_kv_channel_parallel.py`:

```python
import os, threading
import pytest
from waferengine.samples.specdec import kv_channel


def _roundtrip(streams, size):
    rx = kv_channel.KvReceiver(bind=("127.0.0.1", 0), streams=streams)
    try:
        blob = bytes((i * 7 + 3) & 0xFF for i in range(size))
        kv_channel.KvSender(rx.address, streams=streams).send("r", blob)
        assert rx.recv("r", timeout=15) == blob
    finally:
        rx.close()


def test_parallel_default_is_16_streams():
    # default (no streams kwarg, no env) resolves to 16
    rx = kv_channel.KvReceiver(bind=("127.0.0.1", 0))
    try:
        assert rx._streams == 16
    finally:
        rx.close()


@pytest.mark.parametrize("n", [1, 4, 16, 32])
def test_parallel_roundtrip_various_streams(n):
    _roundtrip(n, 5 * 1024 * 1024 + 123)      # 5 MiB + odd tail, exercises _split remainder


def test_single_stream_floor_is_n1():
    _roundtrip(1, 1 << 20)                     # N=1 == the single-stream floor


def test_tiny_buffer_caps_effective_streams():
    _roundtrip(16, 8)                          # 8 bytes with N=16 -> effective_N=8, no 0-byte streams


def test_two_keys_independent_parallel():
    rx = kv_channel.KvReceiver(bind=("127.0.0.1", 0), streams=8)
    try:
        a = bytes(range(256)) * 100
        b = bytes(reversed(range(256))) * 100
        tx = kv_channel.KvSender(rx.address, streams=8)
        tx.send("A", a); tx.send("B", b)
        assert rx.recv("B", timeout=15) == b
        assert rx.recv("A", timeout=15) == a
    finally:
        rx.close()


def test_streams_from_env(monkeypatch):
    monkeypatch.setenv("IOP_KV_STREAMS", "4")
    rx = kv_channel.KvReceiver(bind=("127.0.0.1", 0))
    try:
        assert rx._streams == 4
    finally:
        rx.close()


def test_streams_kwarg_overrides_env(monkeypatch):
    monkeypatch.setenv("IOP_KV_STREAMS", "4")
    rx = kv_channel.KvReceiver(bind=("127.0.0.1", 0), streams=8)
    try:
        assert rx._streams == 8
    finally:
        rx.close()


def test_invalid_streams_raises():
    with pytest.raises(ValueError):
        kv_channel.KvReceiver(bind=("127.0.0.1", 0), streams=0)


def test_close_stops_accept_thread_parallel():
    rx = kv_channel.KvReceiver(bind=("127.0.0.1", 0), streams=16)
    rx.close()
    assert rx._t.is_alive() is False
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest waferengine/samples/specdec/tests/test_kv_channel_parallel.py -v`
Expected: FAIL (`unexpected keyword argument 'streams'` / `_streams` missing).

- [ ] **Step 3: Refactor `_TcpTransport` to N-stream in `kv_channel.py`**

Port `tcp_pump.py`'s `_split` (front-loaded remainder). Replace the single-frame send/recv:
- Add `def _split(total, n): per=[total//n]*n; [per.__setitem__(i, per[i]+1) for i in range(total-sum(per))]; return per` (or the explicit loop form from `tcp_pump.py`).
- Add `_resolve_streams(explicit)` (env `IOP_KV_STREAMS` default 16; `ValueError` if `<1`).
- Receiver `_handle(conn)`: read the chunk header, then `chunk_len` bytes (via `_recv_exactly`); under the condition lock, store `chunk` at `offset` in `_partial[rid]` (a dict keyed by offset or a preallocated `bytearray(total_len)` written at `offset`), increment `_partial_count[rid]`; when `_partial_count[rid] == n_streams`, move the assembled `bytes` into `_buffers[rid]` and `notify_all()`. `recv(rid)` waits for `rid in _buffers` (unchanged contract).
- Sender `send(peer, rid, buf, streams)`: `eff = min(streams, max(1, len(buf)))`; `per = _split(len(buf), eff)`; compute offsets; spawn `eff` threads, each opens `socket.create_connection(peer)`, `TCP_NODELAY`, sends `header(rid, eff, idx, len(buf), offset, per[idx]) + chunk`; join; collect errors and raise if any.
- Keep the accept thread + `settimeout(0.5)`/`_stop`/`join` close semantics from M1 (the leak fix) — one accept thread regardless of N.
- Thread `streams` into `KvReceiver.__init__`/`KvSender.__init__` (store `self._streams = _resolve_streams(streams)`), and pass to `_TcpTransport`. `KvSender.send` uses `self._streams`.

- [ ] **Step 4: Run to verify they pass + full suite green**

Run: `python3 -m pytest waferengine/samples/specdec/tests/ -q`
Expected: PASS — the new parallel tests + all existing `kv_channel`/PD tests (they use the default backend; both ends now use N=16, still correct). RDMA loopback still skips.

- [ ] **Step 5: Sim regression — pd_sim_check still green over the N-stream default.**

Run: `python3 waferengine/samples/specdec/pd_sim_check.py`
Expected: `PD_SIM_PASS` — the two-process disaggregation now moves KV over 16 loopback streams end-to-end through the real appliances (extra validation the N-stream path works with the appliances). (~3-6 min.)

- [ ] **Step 6: Commit**

```bash
git add waferengine/samples/specdec/kv_channel.py waferengine/samples/specdec/tests/test_kv_channel_parallel.py
git commit -m "feat(specdec): kv_channel TCP backend is N parallel streams (default 16, IOP_KV_STREAMS; N=1 floor) — supersedes single-stream (PD M-par)"
```

---

### Task 2: `IOP_KV_STREAMS` driver wiring + bandwidth harness + A/B docs

**Files:**
- Modify: `waferengine/samples/specdec/driver_main.py` (`_inproc_controller_cmd` forwards `IOP_KV_STREAMS` + `IOP_KV_BACKEND` to BOTH roles)
- Create: `waferengine/samples/specdec/kv_bw_check.py` (a backend/stream-count bandwidth harness — loopback here, real net1 on CS-3)
- Modify: `waferengine/samples/specdec/README.md` (A/B section), `run_e2e_pd.sh` (forward `IOP_KV_STREAMS`)
- Test: `waferengine/samples/specdec/tests/test_kv_bw_check.py` (loopback smoke of the harness)

**Interfaces:**
- Produces:
  - `driver_main._inproc_controller_cmd(...)` forwards `IOP_KV_BACKEND` and `IOP_KV_STREAMS` (when set in the driver env) into BOTH the prefill and decode controller commands, so the two runtimes agree on backend + stream count. No-role command stays byte-identical.
  - `kv_bw_check.py`: `python kv_bw_check.py --backend {tcp,rdma} --streams N --size-mib M --rounds R [--peer host:port | --serve]` — a two-role harness (one process `--serve` binds a `KvReceiver` and recv-loops; the other connects and send-loops), timing `size` transfers and printing GB/s p50. On loopback it validates the harness + shows relative N scaling (memory-bound, NOT representative of net1); on CS-3 (two pods) it's the real leg-④ A/B. Reuses `kv_channel` (no new transport).

- [ ] **Step 1: Write the failing harness smoke test** — `tests/test_kv_bw_check.py`:

```python
import subprocess, sys, json, socket
from pathlib import Path


def test_kv_bw_check_loopback_tcp_reports_gbps(tmp_path):
    # spins the harness in-process (serve thread + client) at a small size, N=4,
    # over loopback; asserts it completes and reports a positive GB/s.
    from waferengine.samples.specdec import kv_bw_check
    res = kv_bw_check.run_loopback(backend="tcp", streams=4, size_mib=2, rounds=3)
    assert res["rounds"] == 3
    assert res["gbps_p50"] > 0.0
    assert res["backend"] == "tcp" and res["streams"] == 4
```

(`kv_bw_check.run_loopback(...)` is a thin in-process entry the CLI also calls, so the test needs no subprocess.)

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest waferengine/samples/specdec/tests/test_kv_bw_check.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement `kv_bw_check.py`** — a `run_loopback(backend, streams, size_mib, rounds)` that binds a `KvReceiver`, sends `rounds` blobs of `size_mib` from a `KvSender` on a thread, times each `send`+`recv` round, returns `{backend, streams, size_mib, rounds, gbps_p50, gbps_p99, ms_p50}`. A `main()` CLI with `--serve` (bind + recv-loop, print bound addr) vs client (`--peer`) mode for the real two-pod CS-3 run, plus `--backend/--streams/--size-mib/--rounds`. GB/s = `size_bytes / seconds / 1e9`. Guard `backend="rdma"` with the existing `RdmaUnavailable` (skips cleanly off-HCA).

- [ ] **Step 4: Wire the driver env forwarding** — in `driver_main._inproc_controller_cmd`, forward `IOP_KV_BACKEND` and `IOP_KV_STREAMS` from the driver env into both role commands (guard: only append when set; no-role command unchanged). Add a regression assertion in `tests/test_pd_driver.py` that a decode-role command with both env vars set includes `IOP_KV_BACKEND=`/`IOP_KV_STREAMS=`, and the no-role command does not.

- [ ] **Step 5: Docs** — README "KV transport A/B (parallel TCP vs RDMA)" section: `backend="tcp"` is N-stream (default 16, `IOP_KV_STREAMS`), `N=1` is the single-stream floor; `backend="rdma"` opt-in; how to run `kv_bw_check.py --serve`/client across two pods; and the verbatim gate:
  `> **PENDING (CS-3 device gate):** the TCP N-stream vs RDMA leg-④ A/B is not yet run on real wafers/net1. Expected (per e17): single-stream ~0.55 GB/s, 16-stream TCP ~12.3 GB/s, RDMA-Write ~12.3 GB/s — TCP and RDMA converge at the 100 GbE line rate for >=16 MiB; RDMA wins on receiver CPU + small frames. Run kv_bw_check.py across two pods (sweep --streams 1/16/32/64) + a full run_e2e_pd.sh with IOP_KV_BACKEND/IOP_KV_STREAMS.`
  Make `run_e2e_pd.sh` forward `IOP_KV_STREAMS` (default 16) + `IOP_KV_BACKEND` (default tcp).

- [ ] **Step 6: Run tests + commit**

Run: `python3 -m pytest waferengine/samples/specdec/tests/ -q`
Expected: PASS (harness smoke + driver forwarding assertion + all prior).

```bash
git add waferengine/samples/specdec/driver_main.py waferengine/samples/specdec/kv_bw_check.py waferengine/samples/specdec/tests/test_kv_bw_check.py waferengine/samples/specdec/tests/test_pd_driver.py waferengine/samples/specdec/README.md waferengine/samples/specdec/run_e2e_pd.sh
git commit -m "feat(specdec): IOP_KV_STREAMS/IOP_KV_BACKEND driver forwarding + kv_bw_check A/B harness + README gate (PD M-par)"
```

---

## Self-Review

**Spec coverage:** parallel-stream TCP baseline superseding single-stream (Task 1, ported from the e17 `tcp_pump` reference), configurable `N` (default 16, `N=1` floor) so CS-3 can sweep; both runtimes agree on backend+streams via driver env forwarding (Task 2); a bandwidth harness (`kv_bw_check.py`) usable loopback-here and net1-on-CS-3 for the real TCP-vs-RDMA A/B; docs + PENDING gate. RDMA backend untouched. Disk-free + `.proto`-unchanged + close-leak-safe all preserved.

**Honest boundary:** loopback validates correctness + harness (memory-bound, NOT the real bandwidth); the real TCP N-stream vs RDMA numbers are the CS-3 gate.

**Type consistency:** `KvReceiver(bind,*,backend="tcp",streams=None)`, `KvSender(peer,*,backend="tcp",streams=None)`, `_resolve_streams(explicit)->int`, `_split(total,n)->list[int]`, chunk header `<rid_len:u32><rid><n_streams:u32><stream_idx:u32><total_len:u64><offset:u64><chunk_len:u64>`, `kv_bw_check.run_loopback(backend,streams,size_mib,rounds)->dict`. Consistent across Tasks 1-2.
