# PD Disaggregation — M1 (control plane + disk-free KV transport) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove the prefill/decode disaggregation *control plane* on the dev box (no SDK, no wafer): the GPU stub triggers prefill via the unchanged protobuf, the gateway routes prefill vs decode to two separate pumps, and a disk-free host KV transport moves a realistically-sized mock KV directly "pod-to-pod".

**Architecture:** Prefill = a commit-only `DraftAdvanceRequest{accepted=0, emitted_ids=prompt, base_len=0}`; the whole prompt rides as `correction_ids`. Routing is executor/gateway-side on `base_len==0` (an internal `FLAG_PREFILL` bit in the leg-2 payload; the `.proto` never changes). KV moves prefill→decode entirely in host RAM over a swappable transport (`kv_channel`, TCP loopback in M1). This plan is milestone **M1** of the design at `docs/superpowers/specs/2026-07-01-pd-disaggregation-design.md`; M2 (two real wafers + net1 TCP) and M3 (RDMA) follow in their own plans.

**Tech Stack:** Python 3 stdlib (socket/struct/threading), pytest, grpcio (already used), the committed protobuf stubs under `waferengine/samples/specdec/proto/`.

## Global Constraints

- **`.proto` files are UNCHANGED.** No new gRPC message, field, or enum. Prefill/decode are expressed in the existing `DraftAdvanceRequest` contents. (Basis: ContextBase `SEOAxhYoeW`.)
- **KV never touches disk.** The KV path is host RAM only: `send(request_id, buf)` → `recv(request_id) -> bytes`. No `.npz`, no temp files, no `cfg["kv_cache_file"]`.
- **Prefill discriminator:** `is_prefill(request)` ⇔ `request.HasField("commit") and request.commit.base_len == 0`. The internal flag is `codec.FLAG_PREFILL = 4` (bit2), OR'd into the existing `flags` word alongside `FLAG_HAS_COMMIT`/`FLAG_HAS_PROPOSAL`.
- **Decode egress stays the batched path** (`VERB_EXCH` / single `MOV32` receive) — relevant to M2 kernels; M1 pumps are stubs but keep the `verb=VERB_EXCH` default.
- **Imports/paths:** modules import via `from waferengine.samples.specdec import ...`; proto stubs resolve through `tests/conftest.py` (`import draft_pb2`, `control_pb2`). Run tests from the repo root (the dir containing `waferengine/`):
  `python3 -m pytest waferengine/samples/specdec/tests/ -v`
- **No behavior change for existing single-pump callers.** `run_session(...)` without `prefill_pump` must behave exactly as today (all existing `tests/test_gateway_frontend.py` cases stay green).

---

### Task 1: codec — `FLAG_PREFILL` + KV sizing

**Files:**
- Modify: `waferengine/samples/specdec/codec.py`
- Test: `waferengine/samples/specdec/tests/test_codec.py`

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `codec.FLAG_PREFILL = 4`
  - `encode_request_payload(*, has_commit, has_proposal, num_accepted, correction_ids, is_prefill=False) -> list[int]` (adds the `is_prefill` kwarg; defaults keep the old behavior).
  - `decode_request_payload(u32s) -> dict` gains key `"is_prefill": bool`.
  - `kv_bytes(cfg: dict) -> int` — `n_layers*2*n_kv_heads*head_dim*kv_dtype_bytes*prefill_len*bsz`.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_codec.py`:

```python
def test_prefill_flag_roundtrip():
    u32s = codec.encode_request_payload(
        has_commit=True, has_proposal=True, num_accepted=0,
        correction_ids=[101, 102, 103], is_prefill=True)
    assert u32s[0] == (codec.FLAG_HAS_COMMIT | codec.FLAG_HAS_PROPOSAL
                       | codec.FLAG_PREFILL)
    info = codec.decode_request_payload(u32s)
    assert info["is_prefill"] is True
    assert info["correction_ids"] == [101, 102, 103]   # prompt rides as corrections


def test_decode_payload_not_prefill_by_default():
    u32s = codec.encode_request_payload(
        has_commit=True, has_proposal=True, num_accepted=3, correction_ids=[999])
    assert codec.decode_request_payload(u32s)["is_prefill"] is False


def test_kv_bytes_qwen3_1p7b():
    cfg = {"n_layers": 28, "n_kv_heads": 8, "head_dim": 128,
           "kv_dtype_bytes": 2, "prefill_len": 256, "bsz": 1}
    assert codec.kv_bytes(cfg) == 29_360_128            # 28 MiB, 28*2*8*128*2*256
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest waferengine/samples/specdec/tests/test_codec.py -k "prefill_flag or not_prefill_by_default or kv_bytes" -v`
Expected: FAIL (`AttributeError: module 'codec' has no attribute 'FLAG_PREFILL'` / `kv_bytes`).

- [ ] **Step 3: Implement in `codec.py`**

After the existing `FLAG_HAS_PROPOSAL = 2` line add:

```python
FLAG_PREFILL = 4    # bit2: this advance is a prefill (prompt ingest), not decode
```

Change `encode_request_payload` signature and flags line:

```python
def encode_request_payload(*, has_commit, has_proposal, num_accepted,
                           correction_ids, is_prefill=False):
    """Pack the engine-necessary delta into the minimal u32 request payload."""
    flags = (FLAG_HAS_COMMIT if has_commit else 0) | \
            (FLAG_HAS_PROPOSAL if has_proposal else 0) | \
            (FLAG_PREFILL if is_prefill else 0)
    _check_u32(num_accepted, "num_accepted")
    for cid in correction_ids:
        _check_u32(cid, "correction_id")
    return [flags, num_accepted, len(correction_ids)] + list(correction_ids)
```

In `decode_request_payload`, add the `is_prefill` key to the returned dict:

```python
    return {
        "has_commit": bool(flags & FLAG_HAS_COMMIT),
        "has_proposal": bool(flags & FLAG_HAS_PROPOSAL),
        "is_prefill": bool(flags & FLAG_PREFILL),
        "num_accepted": num_accepted,
        "correction_ids": correction_ids,
    }
```

Add `kv_bytes` (place after `derive_counts`):

```python
def kv_bytes(cfg: dict) -> int:
    """KV-cache byte count for one request, from the real model dims:
    n_layers * 2(K,V) * n_kv_heads * head_dim * dtype_bytes * seq_len * bsz.

    In the passthrough build the CONTENTS are mocked; only this SIZE is real
    (it sets how much rides the runtime<->runtime channel). Qwen3-1.7B:
    28 layers, 8 kv heads, head_dim 128, bf16 -> 112 KiB/token."""
    return (cfg["n_layers"] * 2 * cfg["n_kv_heads"] * cfg["head_dim"]
            * cfg.get("kv_dtype_bytes", 2) * cfg["prefill_len"] * cfg["bsz"])
```

- [ ] **Step 4: Run to verify they pass (and nothing regressed)**

Run: `python3 -m pytest waferengine/samples/specdec/tests/test_codec.py -v`
Expected: PASS (all, including the pre-existing cases).

- [ ] **Step 5: Commit**

```bash
git add waferengine/samples/specdec/codec.py waferengine/samples/specdec/tests/test_codec.py
git commit -m "feat(specdec): codec FLAG_PREFILL + kv_bytes sizing (PD M1)"
```

---

### Task 2: translate — `is_prefill` + set the flag on prefill requests

**Files:**
- Modify: `waferengine/samples/specdec/translate.py`
- Test: `waferengine/samples/specdec/tests/test_translate.py`

**Interfaces:**
- Consumes: `codec.encode_request_payload(..., is_prefill=...)`, `codec.decode_request_payload` (Task 1).
- Produces:
  - `translate.is_prefill(request) -> bool` (`request.HasField("commit") and request.commit.base_len == 0`).
  - `request_to_payload(request) -> (u32s, k)` now sets `FLAG_PREFILL` when `is_prefill(request)` (signature unchanged; prompt already carried as `correction_ids` because prefill has `accepted=0`).

- [ ] **Step 1: Write the failing tests** — append to `tests/test_translate.py`:

```python
def test_prefill_request_sets_flag_and_carries_prompt():
    import draft_pb2 as dpb
    from waferengine.samples.specdec import codec, translate
    req = dpb.DraftAdvanceRequest(
        request_id="p", expected_version=0, expected_len=0,
        commit=dpb.DraftCommit(round_id=1, base_version=0, base_len=0,
                               accepted_draft_tokens=0, emitted_ids=[101, 102, 103]),
        next_proposal=dpb.NextProposal(round_id=2, k=16))
    assert translate.is_prefill(req) is True
    u32s, k = translate.request_to_payload(req)
    info = codec.decode_request_payload(u32s)
    assert info["is_prefill"] is True
    assert info["correction_ids"] == [101, 102, 103]
    assert k == 16


def test_decode_request_is_not_prefill():
    import draft_pb2 as dpb
    from waferengine.samples.specdec import codec, translate
    req = dpb.DraftAdvanceRequest(
        request_id="d", expected_version=1, expected_len=80,
        commit=dpb.DraftCommit(round_id=2, base_version=1, base_len=80,
                               accepted_draft_tokens=3,
                               emitted_ids=[101, 102, 103, 999]),
        next_proposal=dpb.NextProposal(round_id=3, k=16))
    assert translate.is_prefill(req) is False
    u32s, _ = translate.request_to_payload(req)
    assert codec.decode_request_payload(u32s)["is_prefill"] is False
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest waferengine/samples/specdec/tests/test_translate.py -k "prefill or not_prefill" -v`
Expected: FAIL (`module 'translate' has no attribute 'is_prefill'`).

- [ ] **Step 3: Implement in `translate.py`**

Add the helper above `request_to_payload`:

```python
def is_prefill(request):
    """Prefill = the session's first advance: a commit with base_len == 0
    (accepted=0, emitted_ids=prompt -> the whole prompt is ingested). The
    gateway/executor routes on this; nothing on the gRPC wire tags the mode."""
    return request.HasField("commit") and request.commit.base_len == 0
```

In `request_to_payload`, pass the flag through to `encode_request_payload`:

```python
    u32s = codec.encode_request_payload(
        has_commit=has_commit, has_proposal=has_proposal,
        num_accepted=num_accepted, correction_ids=correction_ids,
        is_prefill=is_prefill(request))
```

- [ ] **Step 4: Run to verify they pass (and translate suite is green)**

Run: `python3 -m pytest waferengine/samples/specdec/tests/test_translate.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add waferengine/samples/specdec/translate.py waferengine/samples/specdec/tests/test_translate.py
git commit -m "feat(specdec): translate.is_prefill + FLAG_PREFILL on first advance (PD M1)"
```

---

### Task 3: mock_verify_host — emit a prefill trigger, then the decode loop

**Files:**
- Modify: `waferengine/samples/specdec/mock_verify_host.py`
- Test: `waferengine/samples/specdec/tests/test_mock_verify_prefill.py` (new)

**Interfaces:**
- Consumes: existing `bench_request`, `expected_accounting`; the gRPC stubs.
- Produces:
  - `MockVerify(rounds, k=16, init_version=0, init_len=80, prompt_ids=None)` — new `prompt_ids` kwarg.
  - `MockVerify.prefill_rtt_ms: float | None` attribute.
  - `mock_verify_host.prefill_request(prompt_ids, k) -> DraftAdvanceRequest`.
  - When `prompt_ids` is set, `OpenStream` sends one prefill command (validated) before the `rounds` decode commands and advances `self.version/self.length` to the post-prompt state.

- [ ] **Step 1: Write the failing test** — new file `tests/test_mock_verify_prefill.py`:

```python
from concurrent import futures

import pytest

grpc = pytest.importorskip("grpc")
import control_pb2_grpc as cpbg  # noqa: E402 — proto dir via conftest

from waferengine.engine.io_pipeline.frame import VERB_EXCH
from waferengine.samples.specdec import mock_verify_host as mvh
from waferengine.samples.specdec.gateway_frontend import run_session


class FakePump:
    def exchange(self, seq, u32s, *, verb=VERB_EXCH):
        return list(range(1, 17))   # 16 deterministic draft ids


def test_mock_verify_emits_and_validates_prefill():
    # 1 prefill (prompt of 3) + 3 decode rounds, all validated by the mock host.
    svc = mvh.MockVerify(rounds=3, k=16, prompt_ids=[101, 102, 103])
    server = grpc.server(futures.ThreadPoolExecutor(4))
    cpbg.add_DraftControlServicer_to_server(svc, server)
    port = server.add_insecure_port("127.0.0.1:0")
    server.start()
    try:
        rtts = run_session(f"127.0.0.1:{port}", FakePump(), 16,
                           draft_service_id="prefill-test")
        assert svc.finished.wait(timeout=10)
        assert svc.failures == []
        assert svc.prefill_rtt_ms is not None
        assert len(rtts) == 4              # 1 prefill + 3 decode
    finally:
        server.stop(0)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest waferengine/samples/specdec/tests/test_mock_verify_prefill.py -v`
Expected: FAIL (`TypeError: __init__() got an unexpected keyword argument 'prompt_ids'`).

- [ ] **Step 3: Implement in `mock_verify_host.py`**

Add a prefill request builder next to `bench_request`:

```python
def prefill_request(prompt_ids, k):
    """A prefill trigger: commit-only-style first advance (base_len=0,
    accepted=0, emitted_ids=prompt) + a proposal to draft the first k."""
    return dpb.DraftAdvanceRequest(
        request_id="prefill", expected_version=0, expected_len=0,
        commit=dpb.DraftCommit(round_id=0, base_version=0, base_len=0,
                               accepted_draft_tokens=0,
                               emitted_ids=list(prompt_ids), reason="prefill"),
        next_proposal=dpb.NextProposal(round_id=1, k=k))
```

Extend `MockVerify.__init__`:

```python
    def __init__(self, rounds, k=16, init_version=0, init_len=80, prompt_ids=None):
        self.rounds, self.k = rounds, k
        self.version, self.length = init_version, init_len
        self.prompt_ids = list(prompt_ids) if prompt_ids else None
        self.prefill_rtt_ms = None
        self.rtts_ms, self.failures = [], []
        self.finished = threading.Event()
        self.aborted = threading.Event()
```

In `OpenStream`, right after the `hello` check and before `for index in range(self.rounds):`, insert the prefill exchange:

```python
            if self.prompt_ids:
                preq = prefill_request(self.prompt_ids, self.k)
                exp = expected_accounting(preq)
                t0 = time.perf_counter()
                yield cpb.VerifyServiceMessage(
                    draft_advance=cpb.DraftAdvanceCommand(
                        request_id="cmd-prefill", request=preq, timeout_ms=5000))
                msg = next(request_iterator)
                self.prefill_rtt_ms = (time.perf_counter() - t0) * 1e3
                if msg.WhichOneof("payload") != "draft_advance_result":
                    self.failures.append("prefill: not a result")
                else:
                    res = msg.draft_advance_result
                    if res.request_id != "cmd-prefill":
                        self.failures.append("prefill: bad request_id")
                    elif res.HasField("error"):
                        self.failures.append(f"prefill: error {res.error.code}")
                    else:
                        r = res.response
                        if r.committed_len != exp["committed_len"]:
                            self.failures.append("prefill: len")
                        if len(r.proposal.draft_ids) != self.k:
                            self.failures.append("prefill: draft_len")
                # decode rounds continue from the post-prompt committed state
                self.version, self.length = \
                    exp["committed_version"], exp["committed_len"]
```

Add the CLI flag in `main` (after `--draft-len`):

```python
    ap.add_argument("--prompt-len", type=int, default=0,
                    help="if >0, send a prefill trigger of this many prompt tokens "
                         "before the decode loop")
```

and build the prompt when constructing the service:

```python
    prompt = list(range(1000, 1000 + args.prompt_len)) if args.prompt_len else None
    svc = MockVerify(args.rounds, k=args.draft_len, prompt_ids=prompt)
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest waferengine/samples/specdec/tests/test_mock_verify_prefill.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add waferengine/samples/specdec/mock_verify_host.py waferengine/samples/specdec/tests/test_mock_verify_prefill.py
git commit -m "feat(specdec): mock_verify_host emits a prefill trigger then decode loop (PD M1)"
```

---

### Task 4: `kv_channel` — disk-free runtime↔runtime KV transport (TCP loopback)

**Files:**
- Create: `waferengine/samples/specdec/kv_channel.py`
- Test: `waferengine/samples/specdec/tests/test_kv_channel.py` (new)

**Interfaces:**
- Consumes: Python stdlib only.
- Produces:
  - `KvReceiver(bind=("0.0.0.0", 0))` with `.address -> (host, port)`, `.recv(request_id, timeout=30.0) -> bytes`, `.close()`.
  - `KvSender(peer)` with `.send(request_id: str, buf: bytes) -> None`.
  - `introduce(sender_cfg, receiver_address) -> KvSender` (the driver-side rendezvous: hand the prefill sender the decode receiver's address).

- [ ] **Step 1: Write the failing tests** — new file `tests/test_kv_channel.py`:

```python
import os

import pytest

from waferengine.samples.specdec import kv_channel


def test_kv_channel_loopback_roundtrip_keyed():
    rx = kv_channel.KvReceiver(bind=("127.0.0.1", 0))
    try:
        tx = kv_channel.introduce(None, rx.address)   # rendezvous
        blob = os.urandom(4 * 1024 * 1024)            # 4 MiB mock KV
        tx.send("req-0", blob)
        assert rx.recv("req-0", timeout=10) == blob
    finally:
        rx.close()


def test_kv_channel_two_keys_independent():
    rx = kv_channel.KvReceiver(bind=("127.0.0.1", 0))
    try:
        tx = kv_channel.KvSender(rx.address)
        a, b = os.urandom(1 << 20), os.urandom(1 << 20)
        tx.send("A", a)
        tx.send("B", b)
        assert rx.recv("B", timeout=10) == b
        assert rx.recv("A", timeout=10) == a
    finally:
        rx.close()


def test_kv_channel_recv_timeout():
    rx = kv_channel.KvReceiver(bind=("127.0.0.1", 0))
    try:
        with pytest.raises(TimeoutError):
            rx.recv("missing", timeout=0.3)
    finally:
        rx.close()
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest waferengine/samples/specdec/tests/test_kv_channel.py -v`
Expected: FAIL (`ModuleNotFoundError: ... kv_channel`).

- [ ] **Step 3: Implement `kv_channel.py`**

```python
"""Disk-free runtime<->runtime KV transport (M1: loopback / underlay TCP).

Invariant: KV never touches disk. The prefill runtime drains KV to a host RAM
buffer and `send()`s it; the decode runtime `recv()`s it into a host RAM buffer
and H2D-loads it. The data-path backend is swappable (TCP now, RDMA-Write in
M3); the interface is send(request_id, buf) / recv(request_id) over raw bytes.

Wire frame (one message per send): <rid_len:u32><rid><payload_len:u64><payload>.
"""
from __future__ import annotations

import socket
import struct
import threading


def _recv_exactly(sock, n):
    parts, got = [], 0
    while got < n:
        chunk = sock.recv(min(1 << 20, n - got))
        if not chunk:
            raise ConnectionError("peer closed mid-frame")
        parts.append(chunk)
        got += len(chunk)
    return b"".join(parts)


def _read_frame(sock):
    (rid_len,) = struct.unpack("<I", _recv_exactly(sock, 4))
    rid = _recv_exactly(sock, rid_len).decode("utf-8")
    (plen,) = struct.unpack("<Q", _recv_exactly(sock, 8))
    return rid, _recv_exactly(sock, plen)


class KvReceiver:
    """Binds a TCP socket; each inbound connection delivers one (rid, payload).
    Payloads are buffered by request_id until claimed by recv()."""

    def __init__(self, bind=("0.0.0.0", 0)):
        self._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._srv.bind(bind)
        self._srv.listen(8)
        self._buffers = {}
        self._cv = threading.Condition()
        self._stop = False
        self._t = threading.Thread(target=self._serve, daemon=True)
        self._t.start()

    @property
    def address(self):
        return self._srv.getsockname()

    def _serve(self):
        while not self._stop:
            try:
                conn, _ = self._srv.accept()
            except OSError:
                return
            threading.Thread(target=self._handle, args=(conn,),
                             daemon=True).start()

    def _handle(self, conn):
        try:
            rid, payload = _read_frame(conn)
            with self._cv:
                self._buffers[rid] = payload
                self._cv.notify_all()
        except (OSError, ConnectionError):
            pass
        finally:
            conn.close()

    def recv(self, request_id, timeout=30.0):
        with self._cv:
            if not self._cv.wait_for(lambda: request_id in self._buffers, timeout):
                raise TimeoutError(f"no KV for {request_id!r} within {timeout}s")
            return self._buffers.pop(request_id)

    def close(self):
        self._stop = True
        try:
            self._srv.close()
        except OSError:
            pass


class KvSender:
    """Connects to a peer KvReceiver and sends one keyed KV buffer per send()."""

    def __init__(self, peer):
        self._peer = tuple(peer)

    def send(self, request_id, buf):
        rid = request_id.encode("utf-8")
        payload = bytes(buf)
        with socket.create_connection(self._peer, timeout=30.0) as s:
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            s.sendall(struct.pack("<I", len(rid)) + rid
                      + struct.pack("<Q", len(payload)) + payload)


def introduce(sender_cfg, receiver_address):
    """Driver-side rendezvous: after launching both workers, hand the prefill
    sender the decode receiver's address so the two connect directly. In M1
    both live in one process over loopback; in M2 the address is the decode
    pod's underlay (net1) endpoint. `sender_cfg` is reserved for M3 (RDMA
    QP/GID handshake) and unused here."""
    return KvSender(receiver_address)
```

- [ ] **Step 4: Run to verify they pass**

Run: `python3 -m pytest waferengine/samples/specdec/tests/test_kv_channel.py -v`
Expected: PASS (all three).

- [ ] **Step 5: Commit**

```bash
git add waferengine/samples/specdec/kv_channel.py waferengine/samples/specdec/tests/test_kv_channel.py
git commit -m "feat(specdec): kv_channel disk-free runtime<->runtime KV transport (TCP, PD M1)"
```

---

### Task 5: gateway_frontend — dual-pump routing (prefill vs decode)

**Files:**
- Modify: `waferengine/samples/specdec/gateway_frontend.py`
- Test: `waferengine/samples/specdec/tests/test_gateway_frontend.py`

**Interfaces:**
- Consumes: `translate.is_prefill` (Task 2), `codec.decode_request_payload` (Task 1).
- Produces: `run_session(addr, pump, draft_len, *, ..., prefill_pump=None)` — new final kwarg. When `prefill_pump` is not None, requests where `translate.is_prefill(cmd.request)` route to `prefill_pump.exchange(...)`; all others route to `pump` (the decode pump). When `prefill_pump` is None the behavior is unchanged.

- [ ] **Step 1: Write the failing test** — append to `tests/test_gateway_frontend.py`:

```python
class RecordingPump:
    """Records each payload it is asked to exchange; returns 16 ids."""
    def __init__(self):
        self.calls = []

    def exchange(self, seq, u32s, *, verb=VERB_EXCH):
        self.calls.append(list(u32s))
        return list(range(1, 17))


def test_run_session_routes_prefill_to_prefill_pump():
    from waferengine.samples.specdec import codec
    prefill_pump, decode_pump = RecordingPump(), RecordingPump()
    svc = mvh.MockVerify(rounds=2, k=16, prompt_ids=[101, 102, 103])
    server = grpc.server(futures.ThreadPoolExecutor(4))
    cpbg.add_DraftControlServicer_to_server(svc, server)
    port = server.add_insecure_port("127.0.0.1:0")
    server.start()
    try:
        run_session(f"127.0.0.1:{port}", decode_pump, 16,
                    draft_service_id="pd-route", prefill_pump=prefill_pump)
        assert svc.finished.wait(timeout=10)
        assert svc.failures == []
    finally:
        server.stop(0)
    # exactly the prefill went to the prefill pump, carrying FLAG_PREFILL
    assert len(prefill_pump.calls) == 1
    assert codec.decode_request_payload(prefill_pump.calls[0])["is_prefill"] is True
    # the two decode rounds went to the decode pump, none flagged prefill
    assert len(decode_pump.calls) == 2
    assert all(not codec.decode_request_payload(u)["is_prefill"]
               for u in decode_pump.calls)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest waferengine/samples/specdec/tests/test_gateway_frontend.py::test_run_session_routes_prefill_to_prefill_pump -v`
Expected: FAIL (`TypeError: run_session() got an unexpected keyword argument 'prefill_pump'`).

- [ ] **Step 3: Implement in `gateway_frontend.py`**

Add `prefill_pump=None` to the signature:

```python
def run_session(addr, pump, draft_len, *, draft_service_id="draft-service-1",
                capabilities=("draft.advance",), max_rounds=None,
                idle_timeout_s=None, verb=VERB_EXCH, prefill_pump=None):
```

In the exchange body, replace the `draft_ids = pump.exchange(...)` line with pump selection. The relevant block becomes:

```python
            seq += 1
            t0 = time.perf_counter()
            target = (prefill_pump if (prefill_pump is not None
                                       and translate.is_prefill(cmd.request))
                      else pump)
            try:
                draft_ids = target.exchange(seq, u32s, verb=verb)
                result.response.CopyFrom(
                    translate.build_response(cmd.request, draft_ids))
            except ExchangeError as e:
                result.error.CopyFrom(
                    cpb.Error(code=503, message=str(e), retryable=True))
```

(The rest of the loop — `k`-mismatch guard, RTT append, `outbox.put`, teardown — is unchanged.)

- [ ] **Step 4: Run to verify it passes (and the whole gateway suite stays green)**

Run: `python3 -m pytest waferengine/samples/specdec/tests/test_gateway_frontend.py -v`
Expected: PASS (new test + all pre-existing single-pump tests).

- [ ] **Step 5: Commit**

```bash
git add waferengine/samples/specdec/gateway_frontend.py waferengine/samples/specdec/tests/test_gateway_frontend.py
git commit -m "feat(specdec): gateway_frontend dual-pump prefill/decode routing (PD M1)"
```

---

### Task 6: PD dev-box end-to-end (protocol + routing + disk-free KV), no SDK

**Files:**
- Create: `waferengine/samples/specdec/tests/test_pd_e2e_local.py`

**Interfaces:**
- Consumes: `mock_verify_host.MockVerify` (Task 3), `run_session(..., prefill_pump=...)` (Task 5), `kv_channel` (Task 4), `codec.kv_bytes`/`decode_request_payload` (Task 1). No production code changes — this task is the M1 capstone that proves the pieces compose.
- Produces: a passing end-to-end test. This is the M1 acceptance gate.

This test wires the full M1 loop: the mock GPU host sends a prefill trigger + decode rounds; the gateway routes prefill to a stub pump that mints a **realistically-sized mock KV** (`codec.kv_bytes`) and ships it disk-free over `kv_channel`; the decode stub pump `recv()`s that KV (verifying size) before decoding. The session key is fixed (`"session-0"`) — one prompt, one KV, consumed by the decode rounds.

- [ ] **Step 1: Write the failing test** — new file `tests/test_pd_e2e_local.py`:

```python
from concurrent import futures

import pytest

grpc = pytest.importorskip("grpc")
import control_pb2_grpc as cpbg  # noqa: E402 — proto dir via conftest

from waferengine.engine.io_pipeline.frame import VERB_EXCH
from waferengine.samples.specdec import mock_verify_host as mvh, codec, kv_channel
from waferengine.samples.specdec.gateway_frontend import run_session

CFG = {"draft_len": 16, "bsz": 1, "top_k": 8,
       "n_layers": 28, "n_kv_heads": 8, "head_dim": 128,
       "kv_dtype_bytes": 2, "prefill_len": 3}       # prefill_len=3 -> ~336 KiB mock KV
SESSION = "session-0"


class PrefillStubPump:
    """On the prefill exchange: mint a mock KV of kv_bytes and send it disk-free."""
    def __init__(self, sender, kv_len):
        self.sender, self.kv_len, self.sent = sender, kv_len, False

    def exchange(self, seq, u32s, *, verb=VERB_EXCH):
        info = codec.decode_request_payload(u32s)
        assert info["is_prefill"] is True
        self.sender.send(SESSION, bytes((i & 0xFF) for i in range(self.kv_len)))
        self.sent = True
        return [(info["num_accepted"] + 1) * 1000 + i for i in range(16)]


class DecodeStubPump:
    """First exchange: receive the KV disk-free and verify size; then decode."""
    def __init__(self, receiver, kv_len):
        self.receiver, self.kv_len, self.kv = receiver, kv_len, None

    def exchange(self, seq, u32s, *, verb=VERB_EXCH):
        if self.kv is None:
            self.kv = self.receiver.recv(SESSION, timeout=10)
            assert len(self.kv) == self.kv_len
        info = codec.decode_request_payload(u32s)
        return [(info["num_accepted"] + 1) * 1000 + i for i in range(16)]


def test_pd_disaggregation_local_e2e():
    kv_len = codec.kv_bytes(CFG)
    rx = kv_channel.KvReceiver(bind=("127.0.0.1", 0))
    try:
        tx = kv_channel.introduce(None, rx.address)     # driver rendezvous
        prefill_pump = PrefillStubPump(tx, kv_len)
        decode_pump = DecodeStubPump(rx, kv_len)
        svc = mvh.MockVerify(rounds=4, k=16, prompt_ids=[101, 102, 103])
        server = grpc.server(futures.ThreadPoolExecutor(4))
        cpbg.add_DraftControlServicer_to_server(svc, server)
        port = server.add_insecure_port("127.0.0.1:0")
        server.start()
        try:
            rtts = run_session(f"127.0.0.1:{port}", decode_pump, 16,
                               draft_service_id="pd-e2e", prefill_pump=prefill_pump)
        finally:
            server.stop(0)
        assert svc.finished.wait(timeout=10)
        assert svc.failures == []                        # oracle accounting green
        assert prefill_pump.sent is True
        assert decode_pump.kv is not None and len(decode_pump.kv) == kv_len
        assert len(rtts) == 5                            # 1 prefill + 4 decode
    finally:
        rx.close()
```

- [ ] **Step 2: Run to verify it fails first, then passes**

Run: `python3 -m pytest waferengine/samples/specdec/tests/test_pd_e2e_local.py -v`
Expected: PASS (all M1 production code from Tasks 1–5 already exists; this test only composes it). If it fails, the failure pinpoints which piece regressed — fix in the owning task, do not patch the test.

- [ ] **Step 3: Run the whole specdec suite (no regressions)**

Run: `python3 -m pytest waferengine/samples/specdec/tests/ -v`
Expected: PASS (all pre-existing + all M1 tests).

- [ ] **Step 4: Commit**

```bash
git add waferengine/samples/specdec/tests/test_pd_e2e_local.py
git commit -m "test(specdec): PD disaggregation dev-box e2e — prefill trigger + routing + disk-free KV (PD M1)"
```

---

## Self-Review

**Spec coverage (M1 slice of `2026-07-01-pd-disaggregation-design.md`):**
- §3 protocol reuse (prefill = commit-only `base_len==0`, `FLAG_PREFILL`, `.proto` unchanged) → Tasks 1, 2, 3.
- §4 disk-free `kv_channel` (send/recv by request_id, TCP backend, rendezvous via `introduce`) → Task 4.
- §5 KV sizing from real config (`kv_bytes`) + mocked contents → Tasks 1, 6.
- §2 lifecycle + dual-pump routing (first advance → prefill, else decode) → Tasks 3, 5.
- §8 milestone **M1** ("control plane, stub, no SDK, dev-box testable") → Task 6 capstone.
- **Deferred to M2/M3 (correctly out of this plan):** real `prefill_pt.csl` / `passthrough.csl` KV-consume, `PrefillAppliance`/`DecodeAppliance`, `driver_main` two-bridge wiring on real wafers, net1 TCP transport, RDMA-Write backend. Noted here so the gap is intentional, not missed.

**Placeholder scan:** none — every step ships real code or an exact command.

**Type consistency:** `FLAG_PREFILL` (int 4), `is_prefill(request) -> bool`, `kv_bytes(cfg) -> int`, `KvReceiver.recv(request_id, timeout) -> bytes` / `.address`, `KvSender.send(request_id, buf)`, `introduce(sender_cfg, receiver_address) -> KvSender`, `run_session(..., prefill_pump=None)` — used identically across Tasks 1–6. The stub pumps expose `.exchange(seq, u32s, *, verb=VERB_EXCH)`, matching the real `ExchangePump.exchange` signature so M2 can swap them for real pumps with no caller change.
