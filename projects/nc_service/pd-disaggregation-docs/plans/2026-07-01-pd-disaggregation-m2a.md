# PD Disaggregation — M2a (CSL kernels + appliances, simfab-validated) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Build the two passthrough CSL kernels and their host appliances for PD disaggregation, and prove the full disk-free KV path (prefill emits KV → `kv_channel` → decode ingests KV via H2D) in the **simulator** (`cs_python` simfab), with a numeric oracle.

**Architecture:** `prefill_pt.csl` (single PE): receive the prompt ingress, emit a `kv_words`-long mock KV blob that is a deterministic function of the prompt. `decode_pt.csl` (single PE, **two** host input streams): stream A loads the `kv_words` KV blob **once** at init (the H2D leg) and reduces it to a `kv_checksum`; stream B is the per-exchange ingress; egress is the draft blobs with `kv_checksum` folded into each sampled slot, so a wrong/absent KV changes the output and is caught. Host `PrefillAppliance`/`DecodeAppliance` wrap these on the backbone `ApplianceSession` (generalized to named multi-stream). A `pd_sim_check` gate runs prefill and decode as two `cs_python` processes that hand the KV over loopback `kv_channel` — the disaggregation topology, in sim.

**Tech Stack:** CSL (SDK 2.10), `cerebras.sdk.runtime.sdkruntimepybind` via `cs_python` simfab, Python 3 host code, pytest for host-only pieces, `cs_python` for sim gates.

## Global Constraints

- **`.proto` files UNCHANGED** (unchanged from M1; M2a touches no proto).
- **KV never touches disk** — `kv_channel` (from M1) carries the KV in host RAM; the sim gate uses it over loopback.
- **Decode egress stays the batched single-`MOV32` receive** (`exchange_batch` semantics: one `receive(draft_len*south_wlts)` then host-side slice).
- **KV size is derived from config** via `codec.kv_bytes(cfg)` (M1). `kv_words(cfg) = kv_bytes(cfg) // 4` (KV is transported/DMA'd as u32 wavelets; assert `kv_bytes % 4 == 0`).
- **CSL rules (verified against the repo):** `.csl` files ASCII-only (the `cslc` lexer rejects non-ASCII even in comments); `SOUTH`/`NORTH`/`EAST`/`WEST` are reserved direction keywords — never use them as identifiers; one fabric per process (prefill and decode appliances CANNOT co-exist in one process — the `pd_sim_check` gate uses two processes). The known-good single-PE template is `kernel/passthrough.csl` + `appliance.py::_build_passthrough` — start from them.
- **Sim configs must keep `kv_words` small.** Use a sim config with `n_layers=7, n_kv_heads=2, head_dim=16, kv_dtype_bytes=2, prefill_len=4, bsz=1` → `kv_bytes = 7*2*2*16*2*4 = 3584` → `kv_words = 896`. Do NOT put the 28 MiB production size through simfab.
- **Sim gates run via** `/home/lexu/Cerebras-SDK-2.10.0/cs_python <gate>.py` and print a single `*_PASS` line on success (mirror `sim_check.py`). Host-only unit tests run from repo root: `python3 -m pytest waferengine/samples/specdec/tests/ -q`.
- **Backbone stays use-case-agnostic:** any generalization of `ApplianceSession` must not embed spec-dec/KV specifics.

---

### Task 1: Generalize `ApplianceSession` to named multi-stream (backbone)

The decode kernel needs **two** host input streams (KV-load + per-exchange ingress); today `ApplianceSession` holds exactly one `in_stream`/`out_stream`. Generalize it to a dict of named streams while keeping the existing single-stream `PassthroughAppliance` working.

**Files:**
- Modify: `waferengine/engine/io_pipeline/executor/appliance_session.py`
- Modify: `waferengine/samples/specdec/appliance.py` (adapt `_build_passthrough` + `PassthroughAppliance` to the new return shape)
- Test: `waferengine/engine/io_pipeline/tests/test_appliance_session_streams.py` (new, host-only — uses a fake build_layout, no SDK)

**Interfaces:**
- Produces:
  - `build_layout(layout) -> dict[str, stream]` — build_layout now returns a **dict** mapping a name to each created stream (e.g. `{"in": in_stream, "out": out_stream}`; decode adds `"kv"`). Backward-compat shim: if a build_layout returns a 2-tuple `(in_stream, out_stream)`, `ApplianceSession` treats it as `{"in": ..., "out": ...}`.
  - `ApplianceSession.send(data, *, stream="in")` and `ApplianceSession.receive(n, *, stream="out")` — the stream defaults preserve every existing call site (`send(u32s)`/`receive(n)`).
  - `ApplianceSession._streams: dict[str, stream]` populated from the build_layout return.

- [ ] **Step 1: Write the failing host-only test** — `tests/test_appliance_session_streams.py`. Since `ApplianceSession.__init__` imports the SDK, test the tuple→dict normalization as a pure staticmethod extracted for testability:

```python
from waferengine.engine.io_pipeline.executor.appliance_session import _normalize_streams


def test_normalize_tuple_streams():
    assert _normalize_streams(("A", "B")) == {"in": "A", "out": "B"}


def test_normalize_dict_streams_passthrough():
    d = {"in": "A", "out": "B", "kv": "K"}
    assert _normalize_streams(d) == d


def test_normalize_rejects_missing_in_out():
    import pytest
    with pytest.raises(ValueError):
        _normalize_streams({"in": "A"})          # no "out"
    with pytest.raises(ValueError):
        _normalize_streams(("only-one",))         # bad tuple
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest waferengine/engine/io_pipeline/tests/test_appliance_session_streams.py -v`
Expected: FAIL (`cannot import name '_normalize_streams'`).

- [ ] **Step 3: Implement**

In `appliance_session.py`, add the helper and use it; generalize send/receive:

```python
def _normalize_streams(built):
    """build_layout may return a dict {name: stream} or a legacy 2-tuple
    (in_stream, out_stream). Normalize to a dict and require at least in+out."""
    if isinstance(built, dict):
        streams = dict(built)
    elif isinstance(built, tuple) and len(built) == 2:
        streams = {"in": built[0], "out": built[1]}
    else:
        raise ValueError(f"build_layout must return a dict or (in,out) tuple, got {built!r}")
    for req in ("in", "out"):
        if req not in streams:
            raise ValueError(f"build_layout streams missing required {req!r}: {list(streams)}")
    return streams
```

In `ApplianceSession.__init__`, replace `self._in_stream, self._out_stream = build_layout(layout)` with:

```python
            self._streams = _normalize_streams(build_layout(layout))
```

Replace `send`/`receive`:

```python
    def send(self, u32s, *, stream="in"):
        buf = np.asarray(u32s, dtype=np.uint32).copy()
        self._rt.send(self._streams[stream], buf, nonblock=False)

    def receive(self, n, *, stream="out"):
        buf = np.zeros(n, dtype=np.uint32)
        self._rt.receive(self._streams[stream], buf, n, nonblock=False)
        return buf
```

(Keep the rest of `receive` identical to the current body — if the current implementation differs, preserve its exact receive call, only adding the `stream` kwarg + dict lookup.)

In `appliance.py`, change `_build_passthrough`'s inner `build_layout` to return `{"in": in_stream, "out": out_stream}` instead of the 2-tuple. `PassthroughAppliance`'s `exchange_batch`/`exchange_stream` already call `self._sess.send(...)`/`self._sess.receive(...)` with defaults — no change needed there.

- [ ] **Step 4: Run to verify host test passes + existing host suite green**

Run: `python3 -m pytest waferengine/engine/io_pipeline/tests/ waferengine/samples/specdec/tests/ -q`
Expected: PASS (the new normalization tests + all existing host tests; SDK-requiring tests are skipped on the dev box as before).

- [ ] **Step 5: Sim regression — the existing passthrough gate still passes**

Run: `/home/lexu/Cerebras-SDK-2.10.0/cs_python waferengine/samples/specdec/sim_check.py`
Expected: `SIM_GATE_G1_PASS` (proves the named-stream refactor didn't break the live single-stream appliance).

- [ ] **Step 6: Commit**

```bash
git add waferengine/engine/io_pipeline/executor/appliance_session.py waferengine/samples/specdec/appliance.py waferengine/engine/io_pipeline/tests/test_appliance_session_streams.py
git commit -m "refactor(iop): ApplianceSession named multi-stream (dict or legacy tuple); passthrough sim gate green (PD M2a)"
```

---

### Task 2: `prefill_pt.csl` + `PrefillAppliance` + prefill sim gate

**Files:**
- Create: `waferengine/samples/specdec/kernel/prefill_pt.csl`
- Modify: `waferengine/samples/specdec/appliance.py` (add `PrefillAppliance` + `_build_prefill`)
- Modify: `waferengine/samples/specdec/codec.py` (add `kv_words(cfg)` + `expected_kv(prompt_ids, kv_words)`)
- Create: `waferengine/samples/specdec/config/v0_sim_pd.json` (small sim config with KV dims)
- Create: `waferengine/samples/specdec/prefill_sim_check.py` (sim gate)
- Test: `waferengine/samples/specdec/tests/test_kv_oracle.py` (host-only: `kv_words`, `expected_kv`)

**Interfaces:**
- Consumes: `codec.kv_bytes` (M1), `ApplianceSession` named-stream (Task 1).
- Produces:
  - `codec.kv_words(cfg) -> int` (`kv_bytes(cfg)//4`; assert divisible).
  - `codec.expected_kv(prompt_ids, kv_words) -> list[int]` — the deterministic oracle KV the prefill kernel must emit: `word j = (prompt_ids[j % len(prompt_ids)] + j) & 0xFFFFFFFF`. (Host mirror of the kernel's fill.)
  - `PrefillAppliance(counts, *, cmaddr=None)` with `prefill(u32s) -> list[int]` returning the `kv_words` KV blob.
  - `prefill_pt.csl` params: `in_wlts, kv_words, in_color, out_color`.

- [ ] **Step 1: Write the failing host-only oracle test** — `tests/test_kv_oracle.py`:

```python
from waferengine.samples.specdec import codec


def test_kv_words_divisible():
    cfg = {"n_layers": 7, "n_kv_heads": 2, "head_dim": 16,
           "kv_dtype_bytes": 2, "prefill_len": 4, "bsz": 1}
    assert codec.kv_bytes(cfg) == 3584
    assert codec.kv_words(cfg) == 896


def test_expected_kv_pattern():
    kv = codec.expected_kv([101, 102, 103], kv_words=5)
    assert kv == [(101 + 0), (102 + 1), (103 + 2), (101 + 3), (102 + 4)]


def test_kv_words_rejects_indivisible():
    import pytest
    with pytest.raises(ValueError):
        codec.kv_words({"n_layers": 1, "n_kv_heads": 1, "head_dim": 1,
                        "kv_dtype_bytes": 1, "prefill_len": 1, "bsz": 1})  # 2 bytes -> ok? adjust
```

(Note: pick the indivisible-case dims so `kv_bytes % 4 != 0`; `n_layers=1,n_kv_heads=1,head_dim=1,kv_dtype_bytes=2,prefill_len=1,bsz=1` = 4 bytes IS divisible — use `kv_dtype_bytes=1,head_dim=1,...` = 2 bytes to force the raise. Implementer: choose dims giving `kv_bytes==2` for the raise case.)

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest waferengine/samples/specdec/tests/test_kv_oracle.py -v`
Expected: FAIL (`module 'codec' has no attribute 'kv_words'`).

- [ ] **Step 3: Implement the host oracle in `codec.py`**

```python
def kv_words(cfg: dict) -> int:
    """KV size in u32 wavelets (the on-fabric / transport unit). kv_bytes must
    be a multiple of 4 (bf16 KV over u32 wavelets => head_dim*... even)."""
    nbytes = kv_bytes(cfg)
    if nbytes % 4 != 0:
        raise ValueError(f"kv_bytes={nbytes} not divisible by 4 (u32 wavelets)")
    return nbytes // 4


def expected_kv(prompt_ids, kv_words):
    """The deterministic mock KV the prefill kernel emits from a prompt:
    word j = (prompt_ids[j % len(prompt_ids)] + j) mod 2^32. Host mirror of the
    kernel fill, so the sim gate can check the chip's egress exactly."""
    n = len(prompt_ids)
    return [((prompt_ids[j % n] + j) & 0xFFFFFFFF) for j in range(kv_words)]
```

- [ ] **Step 4: Run to verify host oracle passes**

Run: `python3 -m pytest waferengine/samples/specdec/tests/test_kv_oracle.py -v`
Expected: PASS.

- [ ] **Step 5: Write `prefill_pt.csl`** (start from `passthrough.csl`; single PE, ASCII-only). Ingress = `in_wlts` u32 `[num_tokens, id0, id1, ...]`; egress = `kv_words` u32 where `outbuf[j] = inbuf[1 + (j % num_tokens)] + j` — i.e. the fill mirrors `expected_kv` applied to the PROMPT IDS (which start at ingress index 1; index 0 is `num_tokens`). The host `expected_kv` is fed the prompt ids (not the header), so the kernel must index `inbuf[1 + (j % num_tokens)]`. `num_tokens = inbuf[0]`.

```
// prefill_pt (PD v1): single PE. Receive in_wlts u32 ingress
// [num_tokens, id0, id1, ...]; emit kv_words u32 mock KV where
// outbuf[j] = ids[j % num_tokens] + j. Deterministic oracle. Loops forever.

param in_wlts: u16;      // ingress u32 count per exchange
param kv_words: u16;     // KV egress u32 count
param in_color: u16;     // host -> PE (LEFT edge)
param out_color: u16;    // PE -> host (RIGHT edge)

const IN: i16 = @as(i16, in_wlts);
const KV: i16 = @as(i16, kv_words);

var inbuf: [IN]u32 = @zeros([IN]u32);
var outbuf: [KV]u32 = @zeros([KV]u32);
const in_mem_dsd  = @get_dsd(mem1d_dsd, .{ .base_address = &inbuf,  .extent = IN });
const out_mem_dsd = @get_dsd(mem1d_dsd, .{ .base_address = &outbuf, .extent = KV });

const in_q:  input_queue  = @get_input_queue(2);
const out_q: output_queue = @get_output_queue(2);
const recv_dsd = @get_dsd(fabin_dsd,  .{ .extent = IN, .input_queue  = in_q });
const send_dsd = @get_dsd(fabout_dsd, .{ .extent = KV, .output_queue = out_q });

const main_id = @get_local_task_id(8);
const fill_id = @get_local_task_id(9);
const done_id = @get_local_task_id(10);

task main() void {
    @mov32(in_mem_dsd, recv_dsd, .{ .async = true, .activate = fill_id });
}

task fill() void {
    var ntok: u16 = @as(u16, inbuf[0]);
    var j: u16 = 0;
    while (j < kv_words) : (j += 1) {
        var idx: u16 = 1 + (j % ntok);
        outbuf[@as(i16, j)] = inbuf[@as(i16, idx)] + @as(u32, j);
    }
    @mov32(send_dsd, out_mem_dsd, .{ .async = true, .activate = done_id });
}

task done() void { @activate(main_id); }

comptime {
    @bind_local_task(main, main_id);
    @bind_local_task(fill, fill_id);
    @bind_local_task(done, done_id);
    @initialize_queue(in_q,  .{ .color = @get_color(in_color) });
    @initialize_queue(out_q, .{ .color = @get_color(out_color) });
    @activate(main_id);
}
```

If `cslc` rejects any construct (e.g. `%` on u16, or the `u32 + u16` mix), iterate in simfab via the gate in Step 8 until it compiles and the oracle matches — adjust casts as the compiler requires; the ACCEPTANCE is the gate, keep the fill semantics equal to `expected_kv`.

- [ ] **Step 6: Add `PrefillAppliance` + `_build_prefill` in `appliance.py`** (mirror `_build_passthrough`; ingress port LEFT `in_wlts`, egress port RIGHT `kv_words`; return `{"in": in_stream, "out": out_stream}`):

```python
def _build_prefill(counts, kernel_file="prefill_pt.csl"):
    kernel_path = str(HERE / "kernel" / kernel_file)

    def build_layout(layout):
        from cerebras.sdk.runtime.sdkruntimepybind import (  # noqa: PLC0415
            Edge, Route, RoutingPosition)
        rg = layout.create_code_region(kernel_path, "pf", 1, 1)
        in_c, out_c = rg.color("in_color"), rg.color("out_color")
        rg.set_param_all("in_wlts", counts["in_wlts"])
        rg.set_param_all("kv_words", counts["kv_words"])
        rg.set_param_all("in_color", in_c)
        rg.set_param_all("out_color", out_c)
        rg.paint_all(in_c,  [RoutingPosition().set_input([Route.RAMP]).set_output([Route.RAMP])])
        rg.paint_all(out_c, [RoutingPosition().set_input([Route.RAMP]).set_output([Route.EAST])])
        in_port = rg.create_input_port(in_c, Edge.LEFT,
            [RoutingPosition().set_output([Route.RAMP])], counts["in_wlts"])
        out_port = rg.create_output_port(out_c, Edge.RIGHT,
            [RoutingPosition().set_input([Route.RAMP])], counts["kv_words"], prefix="pf_out")
        rg.place(4, 4)
        return {"in": layout.create_input_stream(in_port),
                "out": layout.create_output_stream(out_port)}
    return build_layout


class PrefillAppliance:
    def __init__(self, counts, *, cmaddr=None):
        self._counts = counts
        self._sess = ApplianceSession(_build_prefill(counts), cmaddr=cmaddr)

    def prefill(self, u32s):
        c = self._counts
        assert len(u32s) <= c["in_wlts"], "prefill ingress exceeds in_wlts"
        self._sess.send(list(u32s) + [0] * (c["in_wlts"] - len(u32s)))
        return [int(x) for x in self._sess.receive(c["kv_words"])]

    def stop(self):
        self._sess.stop()
```

`counts` must include `kv_words`: extend `codec.derive_counts` to also read the KV dims and set `counts["kv_words"] = kv_words(cfg)` when the KV dims are present (guard with `if all(k in cfg for k in (...))` so the existing decode-only configs still work).

- [ ] **Step 7: Create the sim config** `config/v0_sim_pd.json`:

```json
{"draft_len": 16, "bsz": 1, "top_k": 8,
 "n_layers": 7, "n_kv_heads": 2, "head_dim": 16, "kv_dtype_bytes": 2, "prefill_len": 4}
```

- [ ] **Step 8: Write the prefill sim gate** `prefill_sim_check.py` (mirror `sim_check.py`'s structure; run via cs_python). It builds a `PrefillAppliance` on the sim config, sends a known prompt as `[num_tokens, ids...]`, receives `kv_words`, and asserts it equals `codec.expected_kv(prompt_ids, kv_words)`:

```python
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from waferengine.samples.specdec import codec
from waferengine.samples.specdec.appliance import PrefillAppliance

cfg = json.loads((Path(__file__).parent / "config" / "v0_sim_pd.json").read_text())
counts = codec.derive_counts(cfg)
prompt = [101, 102, 103, 104]
app = PrefillAppliance(counts)
try:
    ingress = [len(prompt)] + prompt          # [num_tokens, ids...]
    kv = app.prefill(ingress)
    exp = codec.expected_kv(prompt, counts["kv_words"])
    assert kv == exp, f"KV mismatch: got {kv[:8]}... exp {exp[:8]}..."
    print("PREFILL_SIM_PASS")
finally:
    app.stop()
```

- [ ] **Step 9: Run the prefill sim gate**

Run: `/home/lexu/Cerebras-SDK-2.10.0/cs_python waferengine/samples/specdec/prefill_sim_check.py`
Expected: `PREFILL_SIM_PASS`. Iterate the CSL (Step 5) in simfab until this passes; the host oracle `expected_kv` is the source of truth.

- [ ] **Step 10: Commit**

```bash
git add waferengine/samples/specdec/kernel/prefill_pt.csl waferengine/samples/specdec/appliance.py waferengine/samples/specdec/codec.py waferengine/samples/specdec/config/v0_sim_pd.json waferengine/samples/specdec/prefill_sim_check.py waferengine/samples/specdec/tests/test_kv_oracle.py
git commit -m "feat(specdec): prefill_pt.csl emits prompt-deterministic KV + PrefillAppliance; PREFILL_SIM_PASS (PD M2a)"
```

---

### Task 3: `decode_pt.csl` (KV-consuming, 2 input streams) + `DecodeAppliance` + decode sim gate

**Files:**
- Create: `waferengine/samples/specdec/kernel/decode_pt.csl`
- Modify: `waferengine/samples/specdec/appliance.py` (`DecodeAppliance` + `_build_decode`)
- Modify: `waferengine/samples/specdec/codec.py` (`kv_checksum(kv_list) -> int`)
- Create: `waferengine/samples/specdec/decode_sim_check.py`
- Test: extend `tests/test_kv_oracle.py` (host `kv_checksum`)

**Interfaces:**
- Consumes: `PrefillAppliance` (Task 2), named multi-stream `ApplianceSession` (Task 1), `codec.expected_kv`.
- Produces:
  - `codec.kv_checksum(kv_list) -> int` — `reduce(xor, kv_list, 0) & 0xFFFFFFFF`. Host mirror of the kernel's KV reduction.
  - `DecodeAppliance(counts, *, cmaddr=None)`: `load_kv(kv_list)` sends `kv_words` u32 once (H2D) on the `"kv"` stream; `exchange_batch(u32s) -> list[int]` per exchange (one `receive(draft_len*south_wlts)`, slice sampled slots).
  - `decode_pt.csl` params: `in_wlts, south_wlts, draft_len, sampled_off, kv_words, kv_color, in_color, out_color`. Per exchange, blob i sampled slot = `ingress[i] + kv_checksum`.

- [ ] **Step 1: Write the failing host `kv_checksum` test** — append to `tests/test_kv_oracle.py`:

```python
def test_kv_checksum_xor():
    from functools import reduce
    from operator import xor
    kv = [1, 2, 4, 8]
    assert codec.kv_checksum(kv) == reduce(xor, kv, 0)   # == 15


def test_decode_folds_kv_checksum_expectation():
    # host model of the decode oracle: blob i sampled slot = ingress[i] + checksum
    kv = codec.expected_kv([101, 102, 103, 104], kv_words=896)
    cksum = codec.kv_checksum(kv)
    ingress_ids = [7, 8, 9]
    assert [(x + cksum) & 0xFFFFFFFF for x in ingress_ids] == \
           [ (7 + cksum) & 0xFFFFFFFF, (8 + cksum) & 0xFFFFFFFF, (9 + cksum) & 0xFFFFFFFF ]
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest waferengine/samples/specdec/tests/test_kv_oracle.py -k checksum -v`
Expected: FAIL (`no attribute 'kv_checksum'`).

- [ ] **Step 3: Implement `codec.kv_checksum`**

```python
def kv_checksum(kv_list) -> int:
    """XOR reduction of the KV words (host mirror of the decode kernel's KV
    reduce). A wrong/absent KV changes this, so the decode output diverges."""
    acc = 0
    for w in kv_list:
        acc ^= (w & 0xFFFFFFFF)
    return acc & 0xFFFFFFFF
```

- [ ] **Step 4: Run to verify host test passes**

Run: `python3 -m pytest waferengine/samples/specdec/tests/test_kv_oracle.py -k checksum -v`
Expected: PASS.

- [ ] **Step 5: Write `decode_pt.csl`** — single PE, **two** input queues. At init: one `@mov32` pulls `kv_words` from the KV fabin into `kvbuf`, then a `reduce` task XORs `kvbuf` into `kv_cksum`, then activates the per-exchange `main`. Per exchange: `@mov32` pulls `in_wlts` ingress into `inbuf`, `fill` writes `draft_len` blobs (`outbuf[i*south_wlts + sampled_off] = inbuf[i] + kv_cksum`), `@mov32` sends, `done` re-arms `main` (NOT the KV load — KV loads once). Start from `passthrough.csl`; add the second input queue/color and the init KV path. ASCII-only; do not name anything `SOUTH/NORTH/EAST/WEST`.

Structure (fill in against the compiler in simfab; ACCEPTANCE = Step 9 gate):

```
param in_wlts: u16; param south_wlts: u16; param draft_len: u16;
param sampled_off: u16; param kv_words: u16;
param kv_color: u16; param in_color: u16; param out_color: u16;

const IN: i16 = @as(i16, in_wlts);
const KV: i16 = @as(i16, kv_words);
const OUT_TOTAL: i16 = @as(i16, south_wlts) * @as(i16, draft_len);

var kvbuf:  [KV]u32 = @zeros([KV]u32);
var inbuf:  [IN]u32 = @zeros([IN]u32);
var outbuf: [OUT_TOTAL]u32 = @zeros([OUT_TOTAL]u32);
var kv_cksum: u32 = 0;

const kv_mem_dsd  = @get_dsd(mem1d_dsd, .{ .base_address = &kvbuf,  .extent = KV });
const in_mem_dsd  = @get_dsd(mem1d_dsd, .{ .base_address = &inbuf,  .extent = IN });
const out_mem_dsd = @get_dsd(mem1d_dsd, .{ .base_address = &outbuf, .extent = OUT_TOTAL });

const kv_q: input_queue  = @get_input_queue(3);
const in_q: input_queue  = @get_input_queue(2);
const out_q: output_queue = @get_output_queue(2);
const kv_recv_dsd = @get_dsd(fabin_dsd,  .{ .extent = KV, .input_queue = kv_q });
const recv_dsd    = @get_dsd(fabin_dsd,  .{ .extent = IN, .input_queue = in_q });
const send_dsd    = @get_dsd(fabout_dsd, .{ .extent = OUT_TOTAL, .output_queue = out_q });

const kvload_id = @get_local_task_id(7);
const reduce_id = @get_local_task_id(8);
const main_id   = @get_local_task_id(9);
const fill_id   = @get_local_task_id(10);
const done_id   = @get_local_task_id(11);

task kvload() void { @mov32(kv_mem_dsd, kv_recv_dsd, .{ .async = true, .activate = reduce_id }); }
task reduce() void {
    var j: u16 = 0;
    while (j < kv_words) : (j += 1) { kv_cksum = kv_cksum ^ kvbuf[@as(i16, j)]; }
    @activate(main_id);
}
task main() void { @mov32(in_mem_dsd, recv_dsd, .{ .async = true, .activate = fill_id }); }
task fill() void {
    var i: u16 = 0;
    while (i < draft_len) : (i += 1) {
        outbuf[@as(i16, i) * @as(i16, south_wlts) + @as(i16, sampled_off)] = inbuf[i] + kv_cksum;
    }
    @mov32(send_dsd, out_mem_dsd, .{ .async = true, .activate = done_id });
}
task done() void { @activate(main_id); }

comptime {
    @bind_local_task(kvload, kvload_id); @bind_local_task(reduce, reduce_id);
    @bind_local_task(main, main_id); @bind_local_task(fill, fill_id);
    @bind_local_task(done, done_id);
    @initialize_queue(kv_q, .{ .color = @get_color(kv_color) });
    @initialize_queue(in_q, .{ .color = @get_color(in_color) });
    @initialize_queue(out_q, .{ .color = @get_color(out_color) });
    @activate(kvload_id);
}
```

- [ ] **Step 6: Add `DecodeAppliance` + `_build_decode` in `appliance.py`** — three ports: `kv` input (LEFT edge, `kv_color`, `kv_words`), `in` input (LEFT edge, `in_color`, `in_wlts`) — use distinct colors so both can share LEFT — and `out` output (RIGHT, `out_color`, `south_wlts*draft_len`). Return `{"kv": kv_stream, "in": in_stream, "out": out_stream}`. `load_kv` sends on `"kv"`; `exchange_batch` sends on `"in"` and receives on `"out"` then slices sampled slots (reuse the `PassthroughAppliance.exchange_batch` slicing: `[blob[i*sw+off] for i in range(dl)]`). If two LEFT-edge input ports collide in routing, place them on different edges (e.g. `kv` on `Edge.TOP`) — resolve against the compiler; keep the host interface identical.

- [ ] **Step 7: Write the decode sim gate** `decode_sim_check.py` — build a `DecodeAppliance` on `v0_sim_pd.json`; `load_kv(known_kv)` where `known_kv = codec.expected_kv([101,102,103,104], kv_words)`; run 2 exchanges of a known ingress; assert each returned sampled id == `(ingress_sampled + kv_checksum(known_kv)) & 0xFFFFFFFF`. Print `DECODE_SIM_PASS`. (The ingress format is the decode request `[flags,num_accepted,num_correction,...]` padded to `in_wlts`; the sampled slot the kernel reads is `inbuf[i]` for blob i — feed a known pattern and compute the expectation from the SAME `inbuf[i]` the kernel indexes.)

- [ ] **Step 8: Run the decode sim gate**

Run: `/home/lexu/Cerebras-SDK-2.10.0/cs_python waferengine/samples/specdec/decode_sim_check.py`
Expected: `DECODE_SIM_PASS`. Iterate the CSL until the KV-folded oracle matches; this proves the KV was H2D-loaded to the chip and used.

- [ ] **Step 9: Run host tests + confirm both sim gates**

Run: `python3 -m pytest waferengine/samples/specdec/tests/ -q` then
`/home/lexu/Cerebras-SDK-2.10.0/cs_python waferengine/samples/specdec/prefill_sim_check.py` and
`/home/lexu/Cerebras-SDK-2.10.0/cs_python waferengine/samples/specdec/decode_sim_check.py`
Expected: host suite green; `PREFILL_SIM_PASS`; `DECODE_SIM_PASS`.

- [ ] **Step 10: Commit**

```bash
git add waferengine/samples/specdec/kernel/decode_pt.csl waferengine/samples/specdec/appliance.py waferengine/samples/specdec/codec.py waferengine/samples/specdec/decode_sim_check.py waferengine/samples/specdec/tests/test_kv_oracle.py
git commit -m "feat(specdec): decode_pt.csl ingests KV (2nd stream, H2D) + folds checksum; DecodeAppliance; DECODE_SIM_PASS (PD M2a)"
```

---

### Task 4: `pd_sim_check` — full disaggregation in simfab (two processes, KV over loopback `kv_channel`)

**Files:**
- Create: `waferengine/samples/specdec/pd_worker.py` (one process: runs EITHER a prefill or a decode appliance, driven by argv, exchanging KV over `kv_channel`)
- Create: `waferengine/samples/specdec/pd_sim_check.py` (parent: launches the two `cs_python` workers, rendezvous, asserts the oracle)

**Interfaces:**
- Consumes: `PrefillAppliance`/`DecodeAppliance` (Tasks 2-3), `kv_channel` (M1), `codec.expected_kv`/`kv_checksum`.
- Produces: `PD_SIM_PASS` — the M2a capstone: prefill (proc A) emits KV → `kv_channel` loopback → decode (proc B) H2D-loads KV → decode output reflects the prompt-derived KV checksum. One fabric per process (the gotcha) is honored by construction.

- [ ] **Step 1: Write `pd_worker.py`** — `--role {prefill,decode}`, `--config`, `--kv-addr host:port` (decode binds a `KvReceiver`; prefill connects a `KvSender`), `--session-id`. Prefill: build `PrefillAppliance`, prefill a fixed prompt, `KvSender.send(session_id, bytes(kv_u32_array))`, print the prompt it used to stdout as JSON. Decode: build `DecodeAppliance`, `KvReceiver.recv(session_id)` → np.frombuffer to u32 list → `load_kv`, run N exchanges of a fixed ingress, print the returned sampled ids as JSON. KV bytes on the wire = the u32 array's raw bytes (`np.asarray(kv, np.uint32).tobytes()`); decode reconstructs with `np.frombuffer(buf, np.uint32)`.

- [ ] **Step 2: Write `pd_sim_check.py`** — parent orchestrator (plain `python3`, but it launches the workers via `cs_python`): start the decode worker first (it prints its bound `KvReceiver` address, or use a fixed loopback port), then the prefill worker pointed at it; capture both workers' JSON stdout; compute the expected decode output from the known prompt (`expected_kv` → `kv_checksum` → `(ingress_i + cksum)`), assert the decode worker's reported sampled ids match. Print `PD_SIM_PASS`. Use a fixed `127.0.0.1` loopback port passed to both workers, with the decode worker signaling readiness (a line on stdout) before the prefill worker connects.

- [ ] **Step 3: Run the capstone gate**

Run: `python3 waferengine/samples/specdec/pd_sim_check.py`
(The parent invokes `cs_python` for each worker internally.)
Expected: `PD_SIM_PASS` — prefill KV crosses the disk-free `kv_channel` and the decode chip's output proves it consumed the right KV.

- [ ] **Step 4: Commit**

```bash
git add waferengine/samples/specdec/pd_worker.py waferengine/samples/specdec/pd_sim_check.py
git commit -m "feat(specdec): pd_sim_check — full PD disaggregation in simfab over disk-free kv_channel; PD_SIM_PASS (PD M2a)"
```

---

## Self-Review

**Spec coverage (M2a slice of the design):** prefill kernel emits realistically-sized KV (Task 2); decode kernel H2D-ingests KV via a 2nd stream and folds it (Task 3, the real H2D-into-decode leg); disk-free `kv_channel` carries KV between two runtimes/processes (Task 4); KV size from config (`kv_words`, Tasks 2-3); backbone stays generic (Task 1 named-stream refactor, no KV specifics). Decode egress is the batched single-receive (Tasks 3-4). One-fabric-per-process honored (Task 4 two processes).

**Deferred to M2b/M3 (intentional):** driver two-bridge orchestration + rendezvous on the resident hot-swap workers; real two-wafer bring-up + net1 TCP; RDMA backend. **Device runs (real wafers) are NOT in M2a** — M2a's acceptance is simfab (`PREFILL_SIM_PASS`/`DECODE_SIM_PASS`/`PD_SIM_PASS`) + host unit tests, all runnable on this box.

**CSL risk note:** Tasks 2-3 give a concrete starting kernel but the ACCEPTANCE is the sim gate — the implementer iterates the CSL in simfab (they have `cs_python`) until the host-mirrored oracle matches. This is explicit, not a placeholder: the oracle functions (`expected_kv`, `kv_checksum`) are the exact spec the kernel must satisfy.

**Type consistency:** `kv_words(cfg)->int`, `expected_kv(prompt_ids, kv_words)->list[int]`, `kv_checksum(kv_list)->int`, `PrefillAppliance.prefill(u32s)->list[int]`, `DecodeAppliance.load_kv(kv_list)`/`exchange_batch(u32s)->list[int]`, `ApplianceSession.send(data,*,stream="in")`/`receive(n,*,stream="out")`, build_layout returns `dict[str,stream]`. Used consistently across Tasks 1-4.
