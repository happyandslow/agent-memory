# PD Disaggregation — M3 (RDMA-Write KV backend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use `- [ ]` checkboxes.

**Goal:** Give `kv_channel` a pluggable data-path backend so the KV transfer can run over **RDMA-Write** (RoCE, ~12.3 GB/s per e17) instead of TCP (~9 GB/s), keeping the TCP control channel for rendezvous. TCP stays the default and only-validated-here path; RDMA is a faithful port of the proven `h2d-playground/rdma-explore` shim, gated to fail/skip cleanly without an HCA.

**Architecture:** Refactor `kv_channel` so `KvSender`/`KvReceiver` delegate the actual byte movement to a backend object (`backend="tcp"` default). Add an `rdma` backend: the receiver registers a destination MR and hands its QP info (`raddr/rkey/qpn/psn/gid`) to the sender over the existing TCP control connection; the sender registers its source buffer, connects the QP, `rdmaw_write`s the KV with an immediate carrying the length, and the receiver `poll_recv`s the imm to know it landed. The RDMA core is `librdmaw.so` (C shim over libibverbs), ported verbatim from `rdma-explore/rdmaw/` (+ its vendored headers + build script). **No HCA on the dev box** → the RDMA backend raises `RdmaUnavailable` cleanly and its loopback test skips; the real RDMA run is a CS-3 gate.

**Tech Stack:** Python 3 (`ctypes`), a small C shim over `libibverbs` (built on CS-3 via `build_rdmaw.sh`), `kv_channel` (M1). Source of truth for the C/ctypes: `WaferEngine` branch `lexu/h2d-explore`, `h2d-playground/rdma-explore/` (port verbatim; the C + ctypes ABI are already validated there).

## Global Constraints

- **`.proto` UNCHANGED**; **KV disk-free**; **decode egress batched** (unchanged from M1/M2).
- **TCP stays the default backend and the only path run/tested on this box.** The RDMA backend MUST NOT be reachable unless explicitly selected (`backend="rdma"` / `IOP_KV_BACKEND=rdma`), and MUST fail with a clear `RdmaUnavailable` (not a crash) when `librdmaw.so`/HCA is absent.
- **Public `kv_channel` API is preserved:** `KvReceiver(bind=...)`/`.address`/`.recv(request_id, timeout)`/`.close()`, `KvSender(peer)`/`.send(request_id, buf)`, `introduce(...)` — callers (M2 handlers) do not change. The backend is an internal/optional kwarg.
- **The RDMA C shim is ported verbatim** from `rdma-explore/rdmaw/{rdmaw.c,rdmaw.h,Makefile,build_rdmaw.sh,loopback_test.c}` + `rdma-explore/vendored/` headers into `waferengine/samples/specdec/rdmaw/` + `.../vendored/`. Do NOT hand-write new verbs C.
- **RDMA tests skip cleanly** when no device/`.so` (mirror `rdma-explore/tests/test_rdmaw_loopback.py`'s skip: env `RDMAW_TEST_DEVICE`/`RDMAW_TEST_GID_IDX`, skip if `librdmaw.so` missing or `rdmaw_open` fails).
- Host tests from repo root: `python3 -m pytest waferengine/samples/specdec/tests/ -q`.

---

### Task 1: `kv_channel` pluggable backend seam (TCP extracted; RDMA-ready)

**Files:**
- Modify: `waferengine/samples/specdec/kv_channel.py`
- Test: `waferengine/samples/specdec/tests/test_kv_channel_backend.py` (new)

**Interfaces:**
- Produces:
  - A backend protocol: an object with `send(request_id: str, buf: bytes) -> None` (sender side) and, on the receiver side, the receiver owns bind/recv. Concretely, factor the current TCP logic into `_TcpTransport` used by `KvReceiver`/`KvSender`, and add a `backend="tcp"` kwarg to both (default preserves today's behavior exactly).
  - `KvReceiver(bind=..., *, backend="tcp")`, `KvSender(peer, *, backend="tcp")`, `introduce(sender_cfg, receiver_address, *, backend="tcp")`.
  - `backend` may also come from `os.environ.get("IOP_KV_BACKEND", "tcp")` when not passed — resolved in one helper `_resolve_backend(explicit)`.
  - `class RdmaUnavailable(RuntimeError)` (defined now; raised by the Task-2 backend).
  - Selecting an unknown backend raises `ValueError`; selecting `"rdma"` in Task 1 (before the backend exists) raises `RdmaUnavailable("rdma backend not built")` — so the seam is testable before the port lands.

- [ ] **Step 1: Write the failing test** — `tests/test_kv_channel_backend.py`:

```python
import os
import pytest
from waferengine.samples.specdec import kv_channel


def test_tcp_backend_is_default_and_roundtrips():
    rx = kv_channel.KvReceiver(bind=("127.0.0.1", 0))            # default backend="tcp"
    try:
        tx = kv_channel.KvSender(rx.address)
        tx.send("r", b"hello-kv")
        assert rx.recv("r", timeout=5) == b"hello-kv"
    finally:
        rx.close()


def test_explicit_tcp_backend_roundtrips():
    rx = kv_channel.KvReceiver(bind=("127.0.0.1", 0), backend="tcp")
    try:
        kv_channel.KvSender(rx.address, backend="tcp").send("r", b"x" * 4096)
        assert rx.recv("r", timeout=5) == b"x" * 4096
    finally:
        rx.close()


def test_unknown_backend_raises():
    with pytest.raises(ValueError):
        kv_channel.KvReceiver(bind=("127.0.0.1", 0), backend="nope")


def test_rdma_backend_unavailable_is_clean():
    # Before/without the built .so, selecting rdma must raise RdmaUnavailable,
    # never crash the process.
    with pytest.raises(kv_channel.RdmaUnavailable):
        kv_channel.KvReceiver(bind=("127.0.0.1", 0), backend="rdma")


def test_backend_from_env(monkeypatch):
    monkeypatch.setenv("IOP_KV_BACKEND", "tcp")
    rx = kv_channel.KvReceiver(bind=("127.0.0.1", 0))
    try:
        assert rx.address[0] == "127.0.0.1"
    finally:
        rx.close()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest waferengine/samples/specdec/tests/test_kv_channel_backend.py -v`
Expected: FAIL (`KvReceiver() got an unexpected keyword argument 'backend'` / no `RdmaUnavailable`).

- [ ] **Step 3: Refactor `kv_channel.py`**

Add `import os`, `class RdmaUnavailable(RuntimeError): pass`, and a resolver:

```python
def _resolve_backend(explicit):
    b = explicit if explicit is not None else os.environ.get("IOP_KV_BACKEND", "tcp")
    if b not in ("tcp", "rdma"):
        raise ValueError(f"unknown kv backend {b!r} (want 'tcp' or 'rdma')")
    if b == "rdma":
        try:
            from waferengine.samples.specdec.rdma_backend import RdmaTransport  # noqa: PLC0415
        except Exception as exc:  # noqa: BLE001
            raise RdmaUnavailable(f"rdma backend not built: {exc}") from exc
        return "rdma", RdmaTransport
    return "tcp", None
```

Keep the existing `_recv_exactly`/`_read_frame`/framing. Thread `backend` through `KvReceiver.__init__`/`KvSender.__init__`/`introduce` — for `"tcp"`, behavior is byte-identical to today (the existing socket logic is the `tcp` path). For `"rdma"`, the resolver imports the Task-2 module (absent now → `RdmaUnavailable`). Store the resolved transport and dispatch send/recv/bind through it. (In Task 1 the RDMA class doesn't exist yet, so `backend="rdma"` always raises `RdmaUnavailable` — exactly what the test asserts.)

- [ ] **Step 4: Run to verify tests pass + no regression**

Run: `python3 -m pytest waferengine/samples/specdec/tests/ -q`
Expected: PASS (new backend tests + all M1/M2 `kv_channel`/PD tests unchanged).

- [ ] **Step 5: Commit**

```bash
git add waferengine/samples/specdec/kv_channel.py waferengine/samples/specdec/tests/test_kv_channel_backend.py
git commit -m "feat(specdec): kv_channel pluggable backend seam (tcp default; rdma-ready, RdmaUnavailable) (PD M3)"
```

---

### Task 2: RDMA-Write backend (port `rdma-explore/rdmaw`) + skip-clean test + CS-3 gate

**Files:**
- Create (ported verbatim from `WaferEngine` `lexu/h2d-explore`): `waferengine/samples/specdec/rdmaw/{rdmaw.c,rdmaw.h,Makefile,build_rdmaw.sh,loopback_test.c}`, `waferengine/samples/specdec/vendored/infiniband/*.h`, `waferengine/samples/specdec/vendored/rdma/*.h`, and `waferengine/samples/specdec/rdmaw_ctypes.py` (the ctypes ABI wrapper).
- Create: `waferengine/samples/specdec/rdma_backend.py` (`RdmaTransport` — single keyed KV buffer over RDMA-Write with TCP-control QP rendezvous)
- Test: `waferengine/samples/specdec/tests/test_rdma_backend.py` (skip-clean loopback, mirrors `rdma-explore/tests/test_rdmaw_loopback.py`)
- Modify: `waferengine/samples/specdec/README.md` (RDMA section + CS-3 gate); `run_e2e_pd.sh` (accept `IOP_KV_BACKEND`)

**Interfaces:**
- Consumes: `rdmaw_ctypes.RdmaContext`/`RdmaQpInfo` (ported), `kv_channel` TCP control framing (Task 1), `kv_channel.RdmaUnavailable`.
- Produces: `RdmaTransport` implementing the same send/recv contract the TCP transport does, so `kv_channel` dispatches to it when `backend="rdma"`. Rendezvous: receiver binds a TCP control socket, accepts, reads the sender's declared byte length, registers a destination `bytearray(length)` MR, sends its `RdmaQpInfo` back; sender registers its source buffer, `connect`s, `write`s with imm=length, polls send CQ; receiver `poll_recv`s the imm → returns the filled buffer keyed by request_id. Raises `RdmaUnavailable` if `librdmaw.so` / device / `rdmaw_open` fails.

- [ ] **Step 1: Port the RDMA source verbatim.** From a checkout of `WaferEngine` (branch `lexu/h2d-explore`) copy these into the sample, preserving contents exactly (they are validated; do NOT rewrite the C):

```bash
WE=/home/lexu/WaferEngine
D=waferengine/samples/specdec
mkdir -p $D/rdmaw $D/vendored/infiniband $D/vendored/rdma
for f in rdmaw/rdmaw.c rdmaw/rdmaw.h rdmaw/Makefile rdmaw/build... ; do : ; done   # see explicit list below
git -C "$WE" show lexu/h2d-explore:h2d-playground/rdma-explore/rdmaw/rdmaw.c        > $D/rdmaw/rdmaw.c
git -C "$WE" show lexu/h2d-explore:h2d-playground/rdma-explore/rdmaw/rdmaw.h        > $D/rdmaw/rdmaw.h
git -C "$WE" show lexu/h2d-explore:h2d-playground/rdma-explore/rdmaw/Makefile       > $D/rdmaw/Makefile
git -C "$WE" show lexu/h2d-explore:h2d-playground/rdma-explore/rdmaw/loopback_test.c> $D/rdmaw/loopback_test.c
git -C "$WE" show lexu/h2d-explore:h2d-playground/rdma-explore/rdmaw/.gitignore     > $D/rdmaw/.gitignore
git -C "$WE" show lexu/h2d-explore:h2d-playground/rdma-explore/build_rdmaw.sh       > $D/rdmaw/build_rdmaw.sh
git -C "$WE" show lexu/h2d-explore:h2d-playground/rdma-explore/rdmaw_ctypes.py      > $D/rdmaw_ctypes.py
git -C "$WE" show lexu/h2d-explore:h2d-playground/rdma-explore/vendored/infiniband/verbs.h                > $D/vendored/infiniband/verbs.h
git -C "$WE" show lexu/h2d-explore:h2d-playground/rdma-explore/vendored/infiniband/verbs_api.h            > $D/vendored/infiniband/verbs_api.h
git -C "$WE" show lexu/h2d-explore:h2d-playground/rdma-explore/vendored/infiniband/ib_user_ioctl_verbs.h  > $D/vendored/infiniband/ib_user_ioctl_verbs.h
git -C "$WE" show lexu/h2d-explore:h2d-playground/rdma-explore/vendored/rdma/ib_user_verbs.h              > $D/vendored/rdma/ib_user_verbs.h
chmod +x $D/rdmaw/build_rdmaw.sh
```

Then fix ONLY the two path assumptions the port needs: (a) `rdmaw_ctypes.py`'s `_SO = Path(__file__).resolve().parent / "rdmaw" / "librdmaw.so"` still resolves correctly (it now sits beside `rdmaw/` — keep it), and (b) `build_rdmaw.sh`'s `../vendored` fallback still points at `$D/vendored` (it does, relative to `rdmaw/`). Verify by reading — do not otherwise edit the ported files.

- [ ] **Step 2: Try to compile the shim (best-effort; may be device-independent).**

Run: `bash waferengine/samples/specdec/rdmaw/build_rdmaw.sh` — this compiles `librdmaw.so` using system or vendored libibverbs headers. It does NOT need an HCA to COMPILE. Record the outcome in the report:
  - If it builds → good (compile-validates the C port); the `.so` still can't RUN without a device.
  - If it fails (no `libibverbs.so` to link on this box) → that is EXPECTED and acceptable; the `.so` is built on CS-3 by this same script. Note it and continue.

- [ ] **Step 3: Write `rdma_backend.py`** — `RdmaTransport` doing a single keyed KV buffer over RDMA-Write with a TCP control channel for the QP-info rendezvous + the declared length. Wrap every `RdmaContext` call so `librdmaw.so`-missing / `rdmaw_open`-fail becomes `kv_channel.RdmaUnavailable`. Structure the send/recv to match how `kv_channel` dispatches (from Task 1). Keep the control-channel framing consistent with the TCP transport's (reuse `_read_frame`-style length prefix for the QP-info + length handshake). Reference `rdma-explore/rdmaw_bench.py` for the exact open→reg→local_info→exchange→connect→write/poll→poll_recv sequence.

- [ ] **Step 4: Write the skip-clean test** — `tests/test_rdma_backend.py`, mirroring `rdma-explore/tests/test_rdmaw_loopback.py`:

```python
import os, pytest
from pathlib import Path
from waferengine.samples.specdec import kv_channel

_SO = Path(kv_channel.__file__).parent / "rdmaw" / "librdmaw.so"
pytestmark = pytest.mark.skipif(
    not _SO.exists() or not os.environ.get("RDMAW_TEST_DEVICE"),
    reason="RDMA loopback needs librdmaw.so + RDMAW_TEST_DEVICE (e.g. rxe0) — skipped off-HCA")


def test_rdma_kv_roundtrip_loopback():
    dev = os.environ["RDMAW_TEST_DEVICE"]
    gid = int(os.environ.get("RDMAW_TEST_GID_IDX", "1"))
    rx = kv_channel.KvReceiver(bind=("127.0.0.1", 0), backend="rdma")
    try:
        blob = bytes(range(256)) * 8
        kv_channel.KvSender(rx.address, backend="rdma").send("r", blob)
        assert rx.recv("r", timeout=15) == blob
    finally:
        rx.close()


def test_rdma_unavailable_off_hca():
    # With no built .so this must be a clean RdmaUnavailable, not a crash.
    if _SO.exists() and os.environ.get("RDMAW_TEST_DEVICE"):
        pytest.skip("HCA present; covered by the loopback test")
    with pytest.raises(kv_channel.RdmaUnavailable):
        kv_channel.KvReceiver(bind=("127.0.0.1", 0), backend="rdma")
```

- [ ] **Step 5: Run the tests (RDMA skips cleanly here) + full suite**

Run: `python3 -m pytest waferengine/samples/specdec/tests/test_rdma_backend.py -v`
Expected: the loopback test SKIPS (no HCA), `test_rdma_unavailable_off_hca` PASSES (clean `RdmaUnavailable`).
Run: `python3 -m pytest waferengine/samples/specdec/tests/ -q`
Expected: full suite green (RDMA loopback skipped), no regression.

- [ ] **Step 6: Docs + runbook** — add a "KV transport backend (TCP / RDMA)" note to `README.md`: `backend="rdma"` / `IOP_KV_BACKEND=rdma`, the build step (`rdmaw/build_rdmaw.sh` on CS-3), the QP-info-over-TCP-control rendezvous, and this verbatim gate:
  `> **PENDING (CS-3 device gate):** RDMA-Write KV transport is not yet run on real hardware — needs librdmaw.so built on the pod (rdmaw/build_rdmaw.sh) + an RoCE HCA. TCP is the validated default. This gate measures TCP vs RDMA leg-④ at 28 MiB (expect ~9 vs ~12.3 GB/s per e17).`
  Make `run_e2e_pd.sh` forward `IOP_KV_BACKEND` (default tcp) to the driver env so a CS-3 run can select rdma.

- [ ] **Step 7: Commit**

```bash
git add waferengine/samples/specdec/rdmaw waferengine/samples/specdec/vendored waferengine/samples/specdec/rdmaw_ctypes.py waferengine/samples/specdec/rdma_backend.py waferengine/samples/specdec/tests/test_rdma_backend.py waferengine/samples/specdec/README.md waferengine/samples/specdec/run_e2e_pd.sh
git commit -m "feat(specdec): RDMA-Write kv_channel backend (ported rdma-explore shim); skip-clean off-HCA; CS-3 gate (PD M3)"
```

---

## Self-Review

**Spec coverage (M3):** `kv_channel` data op is swappable to RDMA-Write with the control channel staying TCP (Task 1 seam + Task 2 QP-rendezvous-over-TCP) — matches the design's "only the per-iter send/recv swaps; rendezvous stays TCP." RDMA core is the proven `rdma-explore` shim, ported verbatim (Task 2). TCP remains default + the only path validated here.

**Honest boundary:** the RDMA path CANNOT run on this box (no HCA); its test skips cleanly and the real TCP-vs-RDMA measurement is a documented CS-3 gate. Best-effort compile of the C shim is attempted (Task 2 Step 2) to catch port errors, but a link failure here is expected and non-blocking. Everything testable-here (backend seam, TCP path, clean `RdmaUnavailable`) is unit-tested.

**Type consistency:** `KvReceiver(bind,*,backend="tcp")`, `KvSender(peer,*,backend="tcp")`, `introduce(...,*,backend="tcp")`, `RdmaUnavailable(RuntimeError)`, `_resolve_backend(explicit)->(name, transport_cls|None)`, `RdmaTransport` (send/recv matching the TCP transport). `rdmaw_ctypes.RdmaContext`/`RdmaQpInfo` used verbatim. Consistent across Tasks 1-2.
