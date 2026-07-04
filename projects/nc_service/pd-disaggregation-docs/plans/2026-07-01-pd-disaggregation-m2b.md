# PD Disaggregation — M2b (two-runtime orchestration under one driver) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use `- [ ]` checkboxes.

**Goal:** Run the two PD runtimes as two resident hot-swap (in-process-patched) workers under one gateway driver, with the prefill worker draining KV and pushing it disk-free over `kv_channel` to the decode worker, which loads it and decodes. The driver introduces the two workers (rendezvous); the KV bytes flow pod-to-pod, never through the driver.

**Architecture:** Reuse M1's `gateway_frontend` dual-pump (prefill/decode routing) + the inproc-patch bridge (×2, one per pod). A new PD `build_handlers` role map runs inside each resident worker: the **prefill** role wraps `PrefillAppliance` and a `KvSender`; the **decode** role wraps `DecodeAppliance` and a `KvReceiver`. Rendezvous: the driver brings up the decode pod first, reads its bound `kv_channel` address from the `__IOP_INIT__` reply, and hands it to the prefill pod's controller env before bringing it up. **KV size, kernels, and the disk-free transport are all already proven in simfab (M2a `PD_SIM_PASS`);** M2b is the real-runtime wiring on top.

**Tech Stack:** Python 3 (host), the io_pipeline inproc-patch bridge, `kv_channel` (M1), `PrefillAppliance`/`DecodeAppliance` (M2a), pytest for the logic; `cerebras.sdk.client` (SdkLauncher) only on CS-3 for the real two-pod run.

## Global Constraints

- **`.proto` UNCHANGED**; **KV disk-free** (only `kv_channel`, host RAM); **decode egress batched** (`exchange_batch`).
- **Roles are selected out-of-band** (env `IOP_ROLE=prefill|decode`), never on the gRPC wire; the resident worker builds exactly one appliance (one fabric per process).
- **Backbone stays use-case-agnostic** — all PD/KV specifics live in the sample (`appliance_handlers.py`, `driver_main.py`), not in `io_pipeline/`.
- **Dependency injection for testability:** the PD handlers and the driver rendezvous take factory callables (appliance factory, `KvSender`/`KvReceiver` factory, bridge factory) defaulting to the real ones, so unit tests substitute fakes + `kv_channel` loopback with no SDK/pod.
- **Device validation is a documented CS-3 gate, NOT run here** (no `cerebras.sdk.client`/two wafers on this box). The unit tests cover the orchestration logic; the real two-pod run is Task 3's runbook + a PENDING marker.
- Run host tests from repo root: `python3 -m pytest waferengine/samples/specdec/tests/ -q`.

---

### Task 1: PD `build_handlers` roles (prefill/decode) wiring appliances + `kv_channel`

**Files:**
- Modify: `waferengine/samples/specdec/appliance_handlers.py`
- Test: `waferengine/samples/specdec/tests/test_pd_handlers.py` (new — fakes + real `kv_channel` loopback)

**Interfaces:**
- Consumes: `codec.decode_request_payload`/`derive_counts` (M1), `kv_channel.KvSender`/`KvReceiver` (M1), `PrefillAppliance`/`DecodeAppliance` (M2a), `frame.VERB_EXCH`.
- Produces:
  - `build_prefill_handlers(cfg, *, appliance_factory=None, sender_factory=None, session=None, peer=None) -> {VERB_EXCH: handler}`. The handler: decode the ingress payload → prompt = `correction_ids` → `app.prefill([len(prompt)] + prompt)` → `sender.send(session, np.asarray(kv, np.uint32).tobytes())` → return `draft_len` mock draft ids `[(num_accepted+1)*1000 + i]`.
  - `build_decode_handlers(cfg, *, appliance_factory=None, receiver=None, session=None) -> {VERB_EXCH: handler}`. The handler: on first call `kv = np.frombuffer(receiver.recv(session), np.uint32).tolist(); app.load_kv(kv)`; every call returns `app.exchange_batch(u32s)`.
  - `build_handlers(args, cfg)` dispatches on `getattr(args, "role", None) or os.environ.get("IOP_ROLE")` → prefill/decode; falls through to the existing stub/real behavior when no PD role is set (unchanged).
  - `decode_kv_address(receiver) -> str` — `"host:port"` of a bound `KvReceiver` (for the driver rendezvous; the decode worker publishes this via `__IOP_INIT__`).

- [ ] **Step 1: Write the failing test** — `tests/test_pd_handlers.py`. Use fake appliances + a real `kv_channel` loopback pair so the KV genuinely crosses a socket:

```python
import numpy as np
from waferengine.engine.io_pipeline.frame import VERB_EXCH
from waferengine.samples.specdec import appliance_handlers as ah, codec, kv_channel


class FakePrefillApp:
    def __init__(self, counts): self.counts = counts
    def prefill(self, ingress):
        ntok = ingress[0]
        return [(ingress[1 + (j % ntok)] + j) & 0xFFFFFFFF for j in range(self.counts["kv_words"])]
    def stop(self): pass


class FakeDecodeApp:
    def __init__(self, counts): self.counts = counts; self.kv = None
    def load_kv(self, kv): self.kv = list(kv)
    def exchange_batch(self, u32s):
        cksum = 0
        for w in self.kv: cksum ^= (w & 0xFFFFFFFF)
        info = codec.decode_request_payload(u32s)
        return [((info["num_accepted"] + 1) * 1000 + i + cksum) & 0xFFFFFFFF
                for i in range(self.counts["draft_len"])]
    def stop(self): pass


CFG = {"draft_len": 16, "bsz": 1, "top_k": 8,
       "n_layers": 7, "n_kv_heads": 2, "head_dim": 16, "kv_dtype_bytes": 2, "prefill_len": 4}


def test_pd_handlers_kv_crosses_channel_and_decode_folds_it():
    counts = codec.derive_counts(CFG)
    rx = kv_channel.KvReceiver(bind=("127.0.0.1", 0))
    try:
        prompt = [101, 102, 103, 104]
        # prefill handler: sends KV over the channel
        ph = ah.build_prefill_handlers(
            CFG, appliance_factory=lambda c: FakePrefillApp(c),
            sender_factory=lambda: kv_channel.KvSender(rx.address),
            session="s0", peer=rx.address)
        preq = codec.encode_request_payload(has_commit=True, has_proposal=True,
                                            num_accepted=0, correction_ids=prompt, is_prefill=True)
        ph[VERB_EXCH](preq)                       # drains + sends KV
        # decode handler: receives + loads KV, folds checksum
        dh = ah.build_decode_handlers(
            CFG, appliance_factory=lambda c: FakeDecodeApp(c),
            receiver=rx, session="s0")
        dreq = codec.encode_request_payload(has_commit=True, has_proposal=True,
                                            num_accepted=3, correction_ids=[9])
        out = dh[VERB_EXCH](dreq)
        exp_kv = codec.expected_kv(prompt, counts["kv_words"])
        cksum = codec.kv_checksum(exp_kv)
        assert out == [((3 + 1) * 1000 + i + cksum) & 0xFFFFFFFF for i in range(16)]
    finally:
        rx.close()


def test_build_handlers_dispatches_on_role(monkeypatch):
    import types
    monkeypatch.setenv("IOP_ROLE", "prefill")
    monkeypatch.setenv("IOP_KV_PEER", "127.0.0.1:5")
    monkeypatch.setenv("IOP_SESSION", "s0")
    # inject fakes via module-level factory hooks the impl exposes for tests
    called = {}
    ah._PREFILL_APP_FACTORY = lambda c: FakePrefillApp(c)
    ah._SENDER_FACTORY = lambda: types.SimpleNamespace(send=lambda s, b: called.setdefault("sent", (s, len(b))))
    try:
        h = ah.build_handlers(types.SimpleNamespace(mode="real", cmaddr=None), CFG)
        assert VERB_EXCH in h
    finally:
        ah._PREFILL_APP_FACTORY = None
        ah._SENDER_FACTORY = None
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest waferengine/samples/specdec/tests/test_pd_handlers.py -v`
Expected: FAIL (`no attribute 'build_prefill_handlers'`).

- [ ] **Step 3: Implement in `appliance_handlers.py`**

Add `import os`, `import numpy as np`, module-level test hooks `_PREFILL_APP_FACTORY = None`, `_DECODE_APP_FACTORY = None`, `_SENDER_FACTORY = None`, and:

```python
def _default_prefill_app(counts):
    from waferengine.samples.specdec.appliance import PrefillAppliance  # noqa: PLC0415
    return PrefillAppliance(counts)

def _default_decode_app(counts):
    from waferengine.samples.specdec.appliance import DecodeAppliance   # noqa: PLC0415
    return DecodeAppliance(counts)

def _parse_addr(s):
    host, port = s.rsplit(":", 1)
    return (host, int(port))

def build_prefill_handlers(cfg, *, appliance_factory=None, sender_factory=None,
                           session=None, peer=None):
    counts = codec.derive_counts(cfg)
    make_app = appliance_factory or _PREFILL_APP_FACTORY or _default_prefill_app
    app = make_app(counts)
    session = session or os.environ.get("IOP_SESSION", "pd-session")
    if sender_factory is None and _SENDER_FACTORY is not None:
        sender_factory = _SENDER_FACTORY
    if sender_factory is None:
        peer = peer or _parse_addr(os.environ["IOP_KV_PEER"])
        from waferengine.samples.specdec.kv_channel import KvSender  # noqa: PLC0415
        sender_factory = lambda: KvSender(peer)   # noqa: E731
    sender = sender_factory()
    dl = counts["draft_len"]

    def exch(u32s):
        info = codec.decode_request_payload(u32s)
        prompt = list(info["correction_ids"])
        kv = app.prefill([len(prompt)] + prompt)
        sender.send(session, np.asarray(kv, dtype=np.uint32).tobytes())
        return [(info["num_accepted"] + 1) * 1000 + i for i in range(dl)]

    return {VERB_EXCH: exch}


def build_decode_handlers(cfg, *, appliance_factory=None, receiver=None, session=None):
    counts = codec.derive_counts(cfg)
    make_app = appliance_factory or _DECODE_APP_FACTORY or _default_decode_app
    app = make_app(counts)
    session = session or os.environ.get("IOP_SESSION", "pd-session")
    if receiver is None:
        from waferengine.samples.specdec.kv_channel import KvReceiver  # noqa: PLC0415
        host = os.environ.get("IOP_KV_HOST", "0.0.0.0")
        port = int(os.environ.get("IOP_KV_PORT", "0"))
        receiver = KvReceiver(bind=(host, port))
    loaded = {"done": False}

    def exch(u32s):
        if not loaded["done"]:
            kv = np.frombuffer(receiver.recv(session), dtype=np.uint32).tolist()
            app.load_kv(kv)
            loaded["done"] = True
        return app.exchange_batch(u32s)

    return {VERB_EXCH: exch}, receiver


def decode_kv_address(receiver):
    host, port = receiver.address
    return f"{host}:{port}"
```

Note `build_decode_handlers` returns `(handlers, receiver)` when it binds its own receiver so the caller can publish the address — but the TEST passes a receiver in and expects just the map. Reconcile: make it always return the `{VERB_EXCH: ...}` map, and expose the bound receiver via a separate `decode_kv_address`. Adjust the test/impl so the return is the map; when the impl creates the receiver internally, stash it on the map's closure and provide `build_decode_handlers(..., return_receiver=False)`; for `build_handlers` (decode role) use `return_receiver=True` to get the receiver for INIT publishing. Keep the unit test calling the map-returning form.

Extend `build_handlers`:

```python
def build_handlers(args, cfg):
    role = getattr(args, "role", None) or os.environ.get("IOP_ROLE")
    if role == "prefill":
        return build_prefill_handlers(cfg)
    if role == "decode":
        handlers, receiver = build_decode_handlers(cfg, return_receiver=True)
        # publish the bound KV address for the driver rendezvous (read via __IOP_INIT__)
        os.environ["IOP_KV_BOUND"] = decode_kv_address(receiver)
        return handlers
    # ... existing stub/real dispatch unchanged ...
```

(Resolve the exact return-shape convention while implementing; the acceptance is the test + a clear single convention documented in the docstrings.)

- [ ] **Step 4: Run to verify tests pass + full host suite green**

Run: `python3 -m pytest waferengine/samples/specdec/tests/ -q`
Expected: PASS (new PD-handler tests + all existing).

- [ ] **Step 5: Commit**

```bash
git add waferengine/samples/specdec/appliance_handlers.py waferengine/samples/specdec/tests/test_pd_handlers.py
git commit -m "feat(specdec): PD build_handlers roles (prefill drains+sends KV / decode recvs+loads KV) over kv_channel (PD M2b)"
```

---

### Task 2: Driver two-bridge + rendezvous (decode-first, publish KV addr to prefill)

**Files:**
- Modify: `waferengine/samples/specdec/driver_main.py` (add a `--pd` path building two inproc bridges + rendezvous; extract the rendezvous sequencing into a pure, testable function)
- Test: `waferengine/samples/specdec/tests/test_pd_driver.py` (new — fake bridges, asserts sequencing + address hand-off)

**Interfaces:**
- Consumes: `InProcessPatchBridge`/`ExchangePump` (existing), M1 `run_session(prefill_pump=...)`, Task 1 handlers.
- Produces:
  - `pd_rendezvous(make_decode_bridge, make_prefill_bridge, *, init_decode, init_prefill) -> (pump_prefill, pump_decode)` — pure orchestration: bring up decode bridge → `addr = init_decode()` (reads `IOP_KV_BOUND` from the decode worker's `__IOP_INIT__` reply) → bring up prefill bridge with `peer=addr` via `init_prefill(addr)` → return the two pumps. All I/O is injected so the test drives it with fakes.
  - `driver_main --pd --config ... --addr <gpu>` wires the real `InProcessPatchBridge`s (each controller_cmd carries `IOP_ROLE`, `IOP_SESSION`, and — for prefill — `IOP_KV_PEER=<decode addr>`), then `run_session(addr, pump_decode, draft_len, prefill_pump=pump_prefill, ...)`.

- [ ] **Step 1: Write the failing test** — `tests/test_pd_driver.py`, driving `pd_rendezvous` with fakes that record ordering:

```python
from waferengine.samples.specdec import driver_main


def test_pd_rendezvous_decode_first_then_prefill_with_addr():
    events = []

    class FakeBridge:
        def __init__(self, name): self.name = name
        def close(self): events.append(("close", self.name))

    def make_decode_bridge():
        events.append(("up", "decode")); return FakeBridge("decode")

    def make_prefill_bridge(peer):
        events.append(("up", "prefill", peer)); return FakeBridge("prefill")

    def init_decode(bridge):
        events.append(("init", "decode")); return "10.27.0.9:41000"   # the published KV addr

    def init_prefill(bridge, peer):
        events.append(("init", "prefill", peer))

    pump_prefill, pump_decode = driver_main.pd_rendezvous(
        make_decode_bridge, make_prefill_bridge,
        init_decode=init_decode, init_prefill=init_prefill,
        pump_factory=lambda b: ("pump", b.name))

    # decode brought up + inited BEFORE prefill; prefill got the decode's addr
    assert events == [
        ("up", "decode"), ("init", "decode"),
        ("up", "prefill", "10.27.0.9:41000"), ("init", "prefill", "10.27.0.9:41000"),
    ]
    assert pump_decode == ("pump", "decode") and pump_prefill == ("pump", "prefill")
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest waferengine/samples/specdec/tests/test_pd_driver.py -v`
Expected: FAIL (`no attribute 'pd_rendezvous'`).

- [ ] **Step 3: Implement `pd_rendezvous` in `driver_main.py`** (pure, injected I/O):

```python
def pd_rendezvous(make_decode_bridge, make_prefill_bridge, *,
                  init_decode, init_prefill, pump_factory):
    """Bring up the decode runtime first, read its published KV address, then
    bring up the prefill runtime pointed at it. Returns (pump_prefill, pump_decode).
    All bring-up/init/pump construction is injected so this is unit-testable
    without pods."""
    decode_bridge = make_decode_bridge()
    kv_addr = init_decode(decode_bridge)          # decode's bound kv_channel addr
    prefill_bridge = make_prefill_bridge(kv_addr)
    init_prefill(prefill_bridge, kv_addr)
    return pump_factory(prefill_bridge), pump_factory(decode_bridge)
```

Then add the `--pd` branch in `main()` that builds the two real `InProcessPatchBridge`s. Each `controller_cmd` sets `IOP_BUILD_HANDLERS=...:build_handlers`, `IOP_ROLE=decode|prefill`, `IOP_SESSION=<id>`, `IOP_CONFIG=<cfg>`; the prefill one additionally sets `IOP_KV_PEER=<addr>` (known only after decode init). `init_decode` sends `__IOP_INIT__` and parses `IOP_KV_BOUND=<host:port>` out of the reply string (the decode worker set it in Task 1); `init_prefill` sends `__IOP_INIT__` after `IOP_KV_PEER` is in the controller env. Wire the result into `run_session(args.addr, pump_decode, args.draft_len, prefill_pump=pump_prefill, ...)`. (The exact `InProcessPatchBridge` init/timeout reuse the existing `--bridge inproc` code; factor the controller_cmd builder so prefill/decode share it with role/env differences.)

- [ ] **Step 4: Run to verify test passes + full host suite green**

Run: `python3 -m pytest waferengine/samples/specdec/tests/ -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add waferengine/samples/specdec/driver_main.py waferengine/samples/specdec/tests/test_pd_driver.py
git commit -m "feat(specdec): driver --pd two-bridge rendezvous (decode-first, publish KV addr to prefill) (PD M2b)"
```

---

### Task 3: CS-3 device runbook + PENDING gate (no execution here)

**Files:**
- Create: `waferengine/samples/specdec/run_e2e_pd.sh` (the two-pod bring-up driver command + mock host, mirroring `run_e2e_inproc.sh`)
- Modify: `waferengine/samples/specdec/README.md` (a "PD disaggregation (two runtimes)" section: topology, the `--pd` command, the rendezvous, and an explicit **PENDING: real two-wafer device run** note — what must be verified on CS-3: `PD_SIM_PASS` already covers sim; the device gate is oracle-green + per-leg latency incl. the net1 KV transfer)

**Interfaces:** none (script + docs). This task ships the reproducible device recipe; it is NOT run on this box (no `cerebras.sdk.client`/two wafers).

- [ ] **Step 1: Write `run_e2e_pd.sh`** — usage `run_e2e_pd.sh <config> <gpu-addr> [rounds]`; `export PYTHONPATH=.`; launches `mock_verify_host.py --prompt-len N` and `driver_main.py --pd --config <config> --addr <gpu-addr> --ready-timeout 1800 --idle-timeout 20 --out _runs/pd_driver.json`. Comment the two-wafer prerequisite + the cs3-runner flow.

- [ ] **Step 2: Document in `README.md`** — add the PD section (topology diagram reference to the design spec, the `--pd` command, the rendezvous description, the disk-free KV note), and a clearly marked:
  `> **PENDING (CS-3 device gate):** the real two-wafer run is not yet executed — needs two concurrent appliance allocations + the csl env on CS-3 (run via the cs3-runner skill). Sim is proven (PD_SIM_PASS); this gate adds oracle-green on real wafers + the per-leg latency breakdown incl. the net1 KV transfer.`

- [ ] **Step 3: Commit**

```bash
git add waferengine/samples/specdec/run_e2e_pd.sh waferengine/samples/specdec/README.md
git commit -m "docs(specdec): PD two-runtime runbook (run_e2e_pd.sh) + README + PENDING CS-3 device gate (PD M2b)"
```

---

## Self-Review

**Spec coverage (M2b):** two runtimes under one driver reusing the hot-swap inproc bridge ×2 (Task 2) + PD role handlers wiring real appliances + disk-free `kv_channel` (Task 1); rendezvous = driver introduces the two workers, they hold the direct connection (Tasks 1-2: decode publishes its bound KV addr via `__IOP_INIT__`, prefill dials it; KV pod-to-pod). Roles out-of-band (env), one fabric per process, backbone generic — all held.

**Explicitly device-pending (Task 3):** the real two-wafer / net1 bring-up is a documented CS-3 gate, not executed here. The orchestration LOGIC is unit-tested with fakes + real `kv_channel` loopback (Tasks 1-2); M2a already proved the appliance+kernel+transport in simfab (`PD_SIM_PASS`).

**Type consistency:** `build_prefill_handlers(cfg,*,appliance_factory,sender_factory,session,peer)->{VERB_EXCH:handler}`; `build_decode_handlers(cfg,*,appliance_factory,receiver,session,return_receiver)`; `decode_kv_address(receiver)->str`; `pd_rendezvous(make_decode_bridge,make_prefill_bridge,*,init_decode,init_prefill,pump_factory)->(pump_prefill,pump_decode)`. Handlers are `handler(u32s)->list[int]` (the serve_core contract). Consistent across Tasks 1-3.
