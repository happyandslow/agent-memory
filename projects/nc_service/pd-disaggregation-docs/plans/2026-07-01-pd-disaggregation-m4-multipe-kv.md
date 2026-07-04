# PD Disaggregation — M4 (multi-PE KV via ported demux/mux fan-out) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax. CSL iteration ACCEPTANCE is always the sim gate — mirror M2a: the host-mirrored oracle (`codec.expected_kv`/`kv_checksum`) is the source of truth, iterate the `.csl` in simfab until the gate is bit-exact.

**Goal:** Make the spec-dec PD KV path **multi-PE** by **porting** (not reinventing) the validated demux/mux fan-out from `h2d-explore/h2d-playground`. Today `prefill_pt.csl`/`decode_pt.csl` are **single-PE**: `SdkLayout.create_input_stream()`/`create_output_stream()` each bind exactly ONE PE on a physical FPGA port, so the KV that can actually enter/leave the chip is capped at one PE's ~48 KB SRAM. A realistic KV (8K-token Qwen3 ≈ 896 MiB) cannot fit. To move an actual-size KV the single host stream must fan across a PE array: a **demux (H2D)** distributes the KV slice-by-slice to a core array, and a **mux (D2H)** collects the array's output back to the single FPGA port. This unblocks (a) a real actual-size on-chip H2D measurement and (b) the chunked recv↔H2D overlap on CS-3.

**Architecture:** Vendor the e3.5 fan-out unit into the sample and re-wire the two appliances:
- **Decode H2D:** the `kv` host stream feeds `demux_adaptor(1×1) → demux(1×N) → kvcore(1×N)`; each of the `N = fanout_w*fanout_h` core PEs receives `kv_words/N` of the KV and XOR-reduces its slice to a **1-word partial checksum**; a `mux(1×N)` collects the `N` partials on-chip into the single decode PE, which XORs them into the global `kv_cksum` it folds into every exchange. Because XOR is associative, `XOR(partials) == XOR(all kv words) == codec.kv_checksum(kv)` — the sim oracle stays **bit-exact and unchanged**. `in`/`out` stay single-PE on the decode PE (small).
- **Prefill D2H:** the (small) prompt is **replicated** `N` times host-side and fed through `demux_adaptor(1×1) → demux(1×N) → pfcore(1×N)`; each core PE generates its contiguous `kv_words/N` slice of the deterministic mock KV (`word j = prompt[j % ntok] + j`, `j` in the PE's slice) and emits it through `mux(1×N) → out` in PE order, so the host reassembles the exact `kv_words` blob `codec.expected_kv` predicts.
- **The KV transport (`kv_channel`, warm/async, M1/M2/M3) is UNCHANGED** — it still moves `kv_words` in host RAM between the two runtimes. Only the *on-chip* H2D (decode ingest) and D2H (prefill emit) become multi-PE. This is what retires the `IOP_KV_XFER_BYTES` host-pad hack: the real `kv_words` now actually enters/exits the chip instead of being zero-padded on the wire and truncated before a single-PE H2D.

**Port source (read in full before Task 1):** `WaferEngine` worktree `/.../h2d-explore/h2d-playground/e3.5-sdklayout-bulk-multisend/` — `demux.py` (`get_demux_adaptor`/`get_x_demux`/`get_b_demux`), `mux.py` (`get_mux`), `buffer.py` (`get_buffer`), `demux_adaptor.csl`, `demux.csl`, `mux.csl`, `buffer.csl`, `run.py` (the `adaptor→b_demux→buffer→mux` chain via `layout.connect`). Bandwidth reference: `bandwidth-test-parallel/{DESIGN.md,src/bw_h2d_direct_kernel_v3.csl,bw_d2h_direct_kernel_v3.csl}` (8–11 GB/s H2D over the direct-link fan-out at ≥128 MiB/stream) and `h2d_playground_overview.md`. Alternate 2-D reference (deferred): `e11-sdklayout-fanout/device/sdklayout_x16x16/{dispatch_pe,compute_pe}.csl`.

**Tech Stack:** CSL (SDK 2.10), `cerebras.sdk.runtime.sdkruntimepybind` via `cs_python` simfab, Python 3 host code, pytest for host-only pieces, `cs_python` for sim gates. The device gate is CS-3 (two wafers) via the `cs3-runner` skill.

## Global Constraints

- **SdkLayout binds ONE PE per physical FPGA port.** `create_input_stream(port)`/`create_output_stream(port)` each connect a single PE on a wafer-edge FPGA port (DESIGN.md §"Critical constraint"). Moving more than one PE's worth of KV through a stream is **impossible without fan-out** — the demux/mux is mandatory, not an optimization.
- **The KV transport is UNCHANGED.** `kv_channel` (M1/M3/M-par, warm+async) still carries `kv_words` in host RAM; the appliance PUBLIC interfaces (`PrefillAppliance.prefill(ingress) -> kv_words`, `DecodeAppliance.load_kv(kv_words)`, `exchange_batch`) are UNCHANGED. Only `_build_prefill`/`_build_decode` (layout) and the kernels change. `pd_worker.py` / `appliance_handlers.py` need no edits for the sim gate.
- **`.proto` files UNCHANGED.** M4 touches no proto.
- **KV never touches disk** — host RAM only, over `kv_channel` loopback in the sim gate.
- **Decode egress stays the batched single-`MOV32` receive** (`exchange_batch`).
- **Oracle stays bit-exact.** `codec.expected_kv` / `codec.kv_checksum` are UNCHANGED and remain the source of truth. The multi-PE build changes *how* the chip produces/consumes the KV, never the values. Global decode checksum = `XOR(per-PE partial checksums)` = `XOR(all kv words)` = `kv_checksum(kv)` (XOR associativity). Prefill reassembly = contiguous PE-ordered slices = `expected_kv(prompt, kv_words)`.
- **KV sizing is multi-PE aware.** `N = fanout_w * fanout_h`; `kv_words_per_pe = kv_words // N`; **assert `kv_words % N == 0`** AND **assert `(kv_words_per_pe*4) % ... ` keeps per-PE SRAM within budget** (each core PE buffers its `kv_words_per_pe` slice → `kv_words_per_pe*4` bytes must fit a PE's ~48 KB usable SRAM; on CS-3 scale `N` up so per-PE stays ≤ ~12K u32). Keep the SIM config tiny: `fanout_w=2, fanout_h=2` (N=4) with the existing `kv_words=896` → `kv_words_per_pe=224` (896 B/PE). Dims are configurable so CS-3 can scale.
- **CSL rules (verified against the repo):** `.csl` files are **ASCII-only** (the `cslc` lexer rejects non-ASCII even in comments — the ported files use box-drawing/arrow chars in comments and MUST be de-unicoded during the port). `SOUTH`/`NORTH`/`EAST`/`WEST` are reserved direction keywords — never identifiers (the ported builders use `Route.NORTH`/`Route.SOUTH` etc., which are fine; do not introduce a variable named `south`). **One fabric per process** in sim — prefill and decode appliances cannot co-exist in one process; the PD sim gate uses two `cs_python` processes.
- **CSL region paths must be ABSOLUTE.** The e3.5 builders use relative `'./demux.csl'` and rely on the process CWD; `ApplianceSession.__init__` `os.chdir`es into the artifact dir before calling `build_layout`, so the ported builders MUST resolve region paths as `str(FANOUT_DIR / "demux.csl")` (this is the ONE required change to the ported python builders).
- **Sim gates** run via `/home/lexu/Cerebras-SDK-2.10.0/cs_python <gate>.py` and print a single `*_PASS` line (mirror `sim_check.py`/`pd_sim_check.py`). Host-only unit tests run from repo root: `python3 -m pytest waferengine/samples/specdec/tests/ -q`.
- **Attribution:** every vendored file carries a header comment naming its source (`h2d-explore/h2d-playground/e3.5-sdklayout-bulk-multisend/<file>`). Port as close to verbatim as possible; the ONLY edits are (a) absolute paths, (b) ASCII de-unicode of comments, (c) the kvcore/pfcore reduce/generate bodies (new kernels, derived from `buffer.csl`).

---

### Task 1: Vendor the fan-out unit (CSL + python builders) into the sample

Lift the e3.5 fan-out into `waferengine/samples/specdec/kernel/fanout/` (CSL) + `waferengine/samples/specdec/fanout_layout.py` (python builders), near-verbatim, with attribution. Prove the ported unit compiles + runs a bit-exact loopback in the specdec tree (`adaptor→demux→buffer→mux` round-trip) — the same topology M4 will specialize.

**Files:**
- Create (ported verbatim + ASCII de-unicode + attribution header): `waferengine/samples/specdec/kernel/fanout/{demux_adaptor.csl,demux.csl,mux.csl,buffer.csl}`
- Create (ported from `demux.py`/`mux.py`/`buffer.py`, absolute-path adapted): `waferengine/samples/specdec/fanout_layout.py`
- Create: `waferengine/samples/specdec/fanout_sim_check.py` (loopback smoke gate)
- Test: `waferengine/samples/specdec/tests/test_fanout_layout.py` (host-only import/signature guard, no SDK)

**Interfaces:**
- Produces (in `fanout_layout.py`, `FANOUT_DIR = Path(__file__).parent / "kernel" / "fanout"`):
  - `get_demux_adaptor(layout, name, batch_size, num_batches) -> (in_port, out_port, region)` — 1×1; H2D single-PE ingress of `batch_size*num_batches`; injects a control wavelet after each batch. Region path `str(FANOUT_DIR / "demux_adaptor.csl")`.
  - `get_b_demux(layout, name, batch_size, width, height) -> (in_port, out_port, region)` — the **vertical** demux (`Edge.TOP` in, `Edge.RIGHT` out); distributes `batch_size` per PE down a `width×height` strip.
  - `get_mux(layout, name, batch_size, width, height) -> (in_port, out_port, region)` — vertical mux (`Edge.LEFT` in, `Edge.TOP` out); collects `batch_size` per PE up to a single-PE top port.
  - `get_buffer(layout, name, pe_length, height) -> (in_port, out_port, region)` — 1×height store-and-forward strip (the base M4's kvcore/pfcore are derived from `buffer.csl`).
  - `FANOUT_DIR` exported for callers.
- The ported builders keep their exact e3.5 bodies (colors via `region.color('in_color')`, `set_param_all`, `paint_all` with the exact `RoutingPosition` FSMs, `create_input_port`/`create_output_port`) — ONLY the `create_code_region` path becomes absolute.

- [ ] **Step 1: Write the failing host-only test** — `tests/test_fanout_layout.py` (import + signature guard; no SDK, so patch the heavy import or test the module's constants/paths):

```python
import inspect
from pathlib import Path
from waferengine.samples.specdec import fanout_layout as fl


def test_fanout_dir_points_at_vendored_csl():
    assert (fl.FANOUT_DIR / "demux.csl").exists()
    assert (fl.FANOUT_DIR / "demux_adaptor.csl").exists()
    assert (fl.FANOUT_DIR / "mux.csl").exists()
    assert (fl.FANOUT_DIR / "buffer.csl").exists()


def test_builder_signatures_match_port():
    assert list(inspect.signature(fl.get_demux_adaptor).parameters) == \
        ["layout", "name", "batch_size", "num_batches"]
    assert list(inspect.signature(fl.get_b_demux).parameters) == \
        ["layout", "name", "batch_size", "width", "height"]
    assert list(inspect.signature(fl.get_mux).parameters) == \
        ["layout", "name", "batch_size", "width", "height"]
    assert list(inspect.signature(fl.get_buffer).parameters) == \
        ["layout", "name", "pe_length", "height"]


def test_vendored_csl_is_ascii():
    for f in ("demux_adaptor.csl", "demux.csl", "mux.csl", "buffer.csl"):
        (fl.FANOUT_DIR / f).read_text().encode("ascii")   # raises if non-ASCII
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest waferengine/samples/specdec/tests/test_fanout_layout.py -v`
Expected: FAIL (`No module named ...fanout_layout`).

- [ ] **Step 3: Vendor the CSL (verbatim + ASCII de-unicode + attribution).** Copy the four `.csl` files, prepend an attribution line, and strip any non-ASCII from comments (the e3.5 `demux_adaptor.csl`/`mux.py` diagrams use box-drawing chars — replace with ASCII `+ - | > v ^`). Example header for each:

```
// Ported near-verbatim from h2d-explore/h2d-playground/e3.5-sdklayout-bulk-multisend/demux.csl
// Only edit vs source: ASCII-de-uniconde comments (cslc lexer rejects non-ASCII). Logic UNCHANGED.
```

Copy commands (adjust `WT` to the h2d-explore worktree root):

```bash
WT=/home/lexu/WaferEngine/.claude/worktrees/h2d-explore/h2d-playground/e3.5-sdklayout-bulk-multisend
D=waferengine/samples/specdec/kernel/fanout
mkdir -p $D
for f in demux_adaptor.csl demux.csl mux.csl buffer.csl; do cp "$WT/$f" "$D/$f"; done
# then: prepend attribution header + run an ASCII scrub on comments in each file.
```

- [ ] **Step 4: Vendor the python builders → `fanout_layout.py`.** Concatenate the bodies of `demux.py` (`get_demux_adaptor`, `get_x_demux`, `get_b_demux`), `mux.py` (`get_mux`), `buffer.py` (`get_buffer`) into ONE module with the attribution header, and change ONLY the region paths to absolute:

```python
"""Ported near-verbatim from h2d-explore/h2d-playground/e3.5-sdklayout-bulk-multisend/
{demux.py, mux.py, buffer.py}. ONLY edit vs source: region paths are absolute
(ApplianceSession chdir's into the artifact dir before build_layout runs), so
relative './demux.csl' would not resolve. Fan-out logic UNCHANGED."""
from pathlib import Path
from cerebras.sdk.runtime.sdkruntimepybind import (   # noqa: PLC0415  (SDK-only)
    Edge, Route, RoutingPosition, get_edge_routing)

FANOUT_DIR = Path(__file__).parent.resolve() / "kernel" / "fanout"

def get_demux_adaptor(layout, name, batch_size, num_batches):
    demux_adaptor = layout.create_code_region(
        str(FANOUT_DIR / "demux_adaptor.csl"), name, 1, 1)     # <-- absolute path
    # ... rest VERBATIM from demux.py ...

def get_b_demux(layout, name, batch_size, width, height):
    demux = layout.create_code_region(
        str(FANOUT_DIR / "demux.csl"), name, width, height)    # <-- absolute path
    # ... rest VERBATIM ...

def get_mux(layout, name, batch_size, width, height):
    mux = layout.create_code_region(
        str(FANOUT_DIR / "mux.csl"), name, width, height)      # <-- absolute path
    # ... rest VERBATIM from mux.py ...

def get_buffer(layout, name, pe_length, height):
    buf = layout.create_code_region(
        str(FANOUT_DIR / "buffer.csl"), name, 1, height)       # <-- absolute path
    # ... rest VERBATIM from buffer.py ...
```

(Keep `get_x_demux` too — the horizontal variant — even though M4 uses the vertical `get_b_demux`; it's part of the faithful unit and costs nothing.)

- [ ] **Step 5: Run the host-only test**

Run: `python3 -m pytest waferengine/samples/specdec/tests/test_fanout_layout.py -v`
Expected: PASS (paths exist, signatures match, CSL ASCII-clean). The `sdkruntimepybind` import inside the builder functions is lazy at call-time, so the module imports without the SDK.

- [ ] **Step 6: Write `fanout_sim_check.py`** — the ported unit's loopback smoke, structured on e3.5 `run.py` but self-contained (one `SdkLayout`, `adaptor → b_demux → buffer → mux`, one send/receive, `np.array_equal` assert). Small dims (`pe_length=64, height=4`). Prints `FANOUT_SIM_PASS`. This proves the vendored CSL+builders compile and round-trip **in the specdec tree** (abs paths, cslc_bin) before any KV specialization:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import numpy as np
from cerebras.sdk.runtime.sdkruntimepybind import (
    SdkLayout, SdkRuntime, SdkTarget, SimfabConfig, get_platform)
from waferengine.samples.specdec.fanout_layout import (
    get_demux_adaptor, get_b_demux, get_mux, get_buffer)

PE_LEN, HEIGHT = 64, 4
CSLC = str(Path(__file__).resolve().parents[2] / "engine/io_pipeline/scripts/cslc_bin")

def main():
    total = PE_LEN * HEIGHT
    platform = get_platform(None, SimfabConfig(dump_core=True), SdkTarget.WSE3)
    layout = SdkLayout(platform)
    (h2d_in, ad_out, ad) = get_demux_adaptor(layout, "adaptor", PE_LEN, HEIGHT); ad.place(1, 0)
    (bd_in, bd_out, bd) = get_b_demux(layout, "b_demux", PE_LEN, 1, HEIGHT); bd.place(3, 0)
    layout.connect(ad_out, bd_in)
    (bf_in, bf_out, bf) = get_buffer(layout, "buf", PE_LEN, HEIGHT); bf.place(5, 0)
    layout.connect(bd_out, bf_in)
    (mx_in, d2h_out, mx) = get_mux(layout, "mux", PE_LEN, 1, HEIGHT); mx.place(7, 0)
    layout.connect(bf_out, mx_in)
    h2d = layout.create_input_stream(h2d_in)
    d2h = layout.create_output_stream(d2h_out)
    art = layout.compile(out_prefix="fanout", cslc_prefix=CSLC)
    rt = SdkRuntime(art, platform, memcpy_required=False); rt.load(); rt.run()
    payload = (np.arange(total, dtype=np.uint32) + 1).copy()
    result = np.zeros(total, dtype=np.uint32)
    rt.send(h2d, payload, nonblock=False)
    rt.receive(d2h, result, total, nonblock=False)
    rt.stop()
    assert np.array_equal(payload, result), "fanout loopback mismatch"
    print("FANOUT_SIM_PASS")

if __name__ == "__main__":
    main()
```

- [ ] **Step 7: Run the fan-out smoke gate**

Run: `/home/lexu/Cerebras-SDK-2.10.0/cs_python waferengine/samples/specdec/fanout_sim_check.py`
Expected: `FANOUT_SIM_PASS`. If `layout.connect`/edge routing complains, resolve placement/edges against the compiler (the e3.5 `run.py` places regions at columns 1,3,5,7 with `place(col,0)` — keep that spacing). ACCEPTANCE is the pass line.

- [ ] **Step 8: Commit**

```bash
git add waferengine/samples/specdec/kernel/fanout waferengine/samples/specdec/fanout_layout.py \
        waferengine/samples/specdec/fanout_sim_check.py waferengine/samples/specdec/tests/test_fanout_layout.py
git commit -m "feat(specdec): vendor e3.5 demux/mux fan-out (CSL + builders) + FANOUT_SIM_PASS loopback (PD M4)"
```

---

### Task 2: Multi-PE KV sizing in `codec.py` + config knobs

Add the fan-out sizing helpers and the config knobs. Pure host, pure stdlib — no SDK.

**Files:**
- Modify: `waferengine/samples/specdec/codec.py` (`fanout_pes`, `kv_words_per_pe`; extend `derive_counts`)
- Modify: `waferengine/samples/specdec/config/v0_sim_pd.json` (add `fanout_w`, `fanout_h`)
- Test: extend `waferengine/samples/specdec/tests/test_kv_oracle.py`

**Interfaces:**
- Produces:
  - `codec.fanout_pes(cfg) -> int` — `cfg.get("fanout_w", 1) * cfg.get("fanout_h", 1)`. Default 1 (=single-PE, back-compat for KV-less/decode-only configs).
  - `codec.kv_words_per_pe(cfg) -> int` — `kv_words(cfg) // fanout_pes(cfg)`; **raises ValueError** if `kv_words % fanout_pes != 0`.
  - `derive_counts(cfg)` also sets `counts["fanout_pes"]` and `counts["kv_words_per_pe"]` **when `kv_words` is present** (guard alongside the existing `kv_dim_keys` block, so decode-only configs stay clean).
  - `expected_kv` / `kv_checksum` UNCHANGED.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_kv_oracle.py`:

```python
def test_fanout_pes_and_per_pe():
    cfg = {"n_layers": 7, "n_kv_heads": 2, "head_dim": 16, "kv_dtype_bytes": 2,
           "prefill_len": 4, "bsz": 1, "fanout_w": 2, "fanout_h": 2}
    assert codec.kv_words(cfg) == 896
    assert codec.fanout_pes(cfg) == 4
    assert codec.kv_words_per_pe(cfg) == 224


def test_fanout_pes_defaults_to_one():
    cfg = {"n_layers": 7, "n_kv_heads": 2, "head_dim": 16, "kv_dtype_bytes": 2,
           "prefill_len": 4, "bsz": 1}
    assert codec.fanout_pes(cfg) == 1
    assert codec.kv_words_per_pe(cfg) == codec.kv_words(cfg)


def test_kv_words_per_pe_rejects_indivisible():
    import pytest
    cfg = {"n_layers": 7, "n_kv_heads": 2, "head_dim": 16, "kv_dtype_bytes": 2,
           "prefill_len": 4, "bsz": 1, "fanout_w": 3, "fanout_h": 1}  # 896 % 3 != 0
    with pytest.raises(ValueError):
        codec.kv_words_per_pe(cfg)


def test_derive_counts_carries_fanout():
    cfg = {"draft_len": 16, "bsz": 1, "top_k": 8, "n_layers": 7, "n_kv_heads": 2,
           "head_dim": 16, "kv_dtype_bytes": 2, "prefill_len": 4,
           "fanout_w": 2, "fanout_h": 2}
    c = codec.derive_counts(cfg)
    assert c["fanout_pes"] == 4 and c["kv_words_per_pe"] == 224
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest waferengine/samples/specdec/tests/test_kv_oracle.py -k fanout -v`
Expected: FAIL (`no attribute 'fanout_pes'`).

- [ ] **Step 3: Implement in `codec.py`**

```python
def fanout_pes(cfg: dict) -> int:
    """Number of core PEs the KV fans across = fanout_w * fanout_h (default 1)."""
    return int(cfg.get("fanout_w", 1)) * int(cfg.get("fanout_h", 1))


def kv_words_per_pe(cfg: dict) -> int:
    """KV u32 words each core PE owns. kv_words must divide evenly across the
    fan-out (each demux batch is exactly this many wavelets)."""
    total, n = kv_words(cfg), fanout_pes(cfg)
    if total % n != 0:
        raise ValueError(f"kv_words={total} not divisible by fanout_pes={n}")
    return total // n
```

In `derive_counts`, inside the existing `if all(k in cfg for k in kv_dim_keys):` block, after `counts["kv_words"] = kv_words(cfg)` add:

```python
        counts["fanout_pes"] = fanout_pes(cfg)
        counts["kv_words_per_pe"] = kv_words_per_pe(cfg)
```

- [ ] **Step 4: Add the config knobs** — `config/v0_sim_pd.json` becomes:

```json
{"draft_len": 16, "bsz": 1, "top_k": 8,
 "n_layers": 7, "n_kv_heads": 2, "head_dim": 16, "kv_dtype_bytes": 2, "prefill_len": 4,
 "fanout_w": 2, "fanout_h": 2}
```

(kv_words=896, fanout_pes=4, kv_words_per_pe=224 — tiny, sim-safe.)

- [ ] **Step 5: Run tests**

Run: `python3 -m pytest waferengine/samples/specdec/tests/test_kv_oracle.py -q`
Expected: PASS (new fanout tests + all prior oracle tests).

- [ ] **Step 6: Commit**

```bash
git add waferengine/samples/specdec/codec.py waferengine/samples/specdec/config/v0_sim_pd.json \
        waferengine/samples/specdec/tests/test_kv_oracle.py
git commit -m "feat(specdec): codec fanout_pes/kv_words_per_pe sizing + fanout_w/h config knobs (PD M4)"
```

---

### Task 3: Decode multi-PE H2D — `kvcore.csl` + decode PE rewrite + `_build_decode` + gate

Route the `kv` host stream through `adaptor→demux→kvcore(1×N)→mux` into the decode PE. Each `kvcore` PE XOR-reduces its `kv_words_per_pe` slice to a 1-word partial; the mux delivers the N partials on-chip to the decode PE, which XORs them into `kv_cksum`. `in`/`out` stay single-PE on the decode PE.

**Files:**
- Create: `waferengine/samples/specdec/kernel/fanout/kvcore.csl` (derived from `buffer.csl`: reduce-not-forward)
- Modify: `waferengine/samples/specdec/kernel/decode_pt.csl` (KV input is now N partial words from the on-chip mux, not `kv_words` from the host)
- Modify: `waferengine/samples/specdec/appliance.py` (`_build_decode` rewrite)
- Modify: `waferengine/samples/specdec/decode_sim_check.py` (uses fanout config; oracle unchanged)
- Test: none new (oracle unchanged); the gate is the acceptance.

**Interfaces:**
- Produces:
  - `kvcore.csl` params: `pe_length: u16` (= `kv_words_per_pe`), `in_color: u16`, `out_color: u16`. Receives `pe_length` u32 (WEST→RAMP), XOR-reduces to `partial: u32`, emits `1` u32 (RAMP→EAST).
  - `decode_pt.csl` gains `kv_pes: u16` (= `fanout_pes`); its `kv` fabin now reads `kv_pes` words (the partials) and the `reduce` task XORs those `kv_pes` words into `kv_cksum`. `kv_words` param is dropped from the decode PE (it no longer sees the whole KV). Everything else (in/out, per-exchange fill) is UNCHANGED.
  - `_build_decode(counts)` builds: `get_demux_adaptor("dec_adaptor", kv_words_per_pe, fanout_pes)`, `get_b_demux("dec_demux", kv_words_per_pe, 1, fanout_pes)`, a `kvcore` region (1×fanout_pes), `get_mux("dec_mux", 1, 1, fanout_pes)`, and the decode PE region (kv-partials input port ← `layout.connect(mux_out, ...)`, `in` host input, `out` host output). Returns `{"kv": <adaptor h2d stream>, "in": <in stream>, "out": <out stream>}`.
  - `DecodeAppliance.load_kv(kv_list)` UNCHANGED — sends `kv_words` on `"kv"`; the adaptor+demux fan it out.

- [ ] **Step 1: Write `kvcore.csl`** (start from vendored `buffer.csl`; ASCII-only; reduce instead of forward):

```
// Derived from h2d-explore .../e3.5/buffer.csl: a 1xN strip PE that, instead of
// forwarding its pe_length slice, XOR-reduces it to a single partial checksum and
// emits ONE u32 east into the mux. XOR is associative, so the decode PE XORing the
// N partials == XORing the whole KV == codec.kv_checksum(kv).
param pe_length: u16;    // = kv_words_per_pe (this PE's KV slice length)
param in_color:  u16;    // demux (WEST) -> RAMP
param out_color: u16;    // RAMP -> mux (EAST)

const input_q  = @get_input_queue(0);
const output_q = @get_output_queue(1);

var buf = @zeros([pe_length]u32);
var partial: [1]u32 = @zeros([1]u32);

const mem_dsd = @get_dsd(mem1d_dsd, .{ .base_address = &buf, .extent = pe_length });
const par_dsd = @get_dsd(mem1d_dsd, .{ .base_address = &partial, .extent = 1 });
const in_dsd  = @get_dsd(fabin_dsd,  .{ .extent = pe_length, .fabric_color = @get_color(in_color),  .input_queue  = input_q });
const out_dsd = @get_dsd(fabout_dsd, .{ .extent = 1,         .fabric_color = @get_color(out_color), .output_queue = output_q });

const recv_id   = @get_local_task_id(8);
const reduce_id = @get_local_task_id(9);
const send_id   = @get_local_task_id(10);

task recv() void { @mov32(mem_dsd, in_dsd, .{ .async = true, .activate = reduce_id }); }
task reduce() void {
    var acc: u32 = 0;
    var j: u16 = 0;
    while (j < pe_length) : (j += 1) { acc = acc ^ buf[@as(i16, j)]; }
    partial[0] = acc;
    @activate(send_id);
}
task send() void { @mov32(out_dsd, par_dsd, .{ .async = true, .activate = recv_id }); }

comptime {
    @bind_local_task(recv,   recv_id);
    @bind_local_task(reduce, reduce_id);
    @bind_local_task(send,   send_id);
    @activate(recv_id);
    @initialize_queue(input_q, .{ .color = @get_color(in_color) });
    if (@is_arch("wse3")) { @initialize_queue(output_q, .{ .color = @get_color(out_color) }); }
}
```

Add a `get_kvcore(layout, name, pe_length, height)` builder to `fanout_layout.py` — a copy of `get_buffer` but the OUTPUT port per-PE width is `1` (not `pe_length`): `out_port = ... create_output_port(out_color, Edge.RIGHT, [out_port_routes], 1 * height)`; input port stays `pe_length * height`. Region path `str(FANOUT_DIR / "kvcore.csl")`.

- [ ] **Step 2: Rewrite `decode_pt.csl`** — swap the `kv` path to read `kv_pes` partials from the on-chip mux and reduce those. Diff vs the current file:

```
param kv_pes: u16;       // number of KV core PEs (= fanout_pes); replaces kv_words on this PE
// (drop: param kv_words)
const KVP: i16 = @as(i16, kv_pes);
var kvbuf: [KVP]u32 = @zeros([KVP]u32);            // was [KV]
const kv_mem_dsd  = @get_dsd(mem1d_dsd, .{ .base_address = &kvbuf, .extent = KVP });
const kv_recv_dsd = @get_dsd(fabin_dsd,  .{ .extent = KVP, .input_queue = kv_q });
// reduce(): while (j < kv_pes) kv_cksum ^= kvbuf[j];   (was kv_words)
```

Everything else (in_q/out_q, main/fill/done, the per-exchange oracle `outbuf[i*south_wlts + sampled_off] = inbuf[i] + kv_cksum`) is UNCHANGED — the folded checksum is numerically identical.

- [ ] **Step 3: Rewrite `_build_decode` in `appliance.py`** — replace the single-PE `kv` port with the fan-out chain, keep `in`/`out` single-PE on the decode PE. Skeleton (resolve exact edges/placement against the compiler, mirror e3.5 `run.py` column spacing):

```python
def _build_decode(counts, kernel_file="decode_pt.csl"):
    kernel_path = str(HERE / "kernel" / kernel_file)
    def build_layout(layout):
        from cerebras.sdk.runtime.sdkruntimepybind import (Edge, Route, RoutingPosition)  # noqa: PLC0415
        from waferengine.samples.specdec.fanout_layout import (  # noqa: PLC0415
            get_demux_adaptor, get_b_demux, get_kvcore, get_mux)
        N   = counts["fanout_pes"]
        ppp = counts["kv_words_per_pe"]
        # --- KV H2D fan-out chain: host kv stream -> adaptor -> demux -> kvcore -> mux ---
        (kv_h2d_in, ad_out, ad) = get_demux_adaptor(layout, "dec_adaptor", ppp, N); ad.place(1, 0)
        (bd_in, bd_out, bd)     = get_b_demux(layout, "dec_demux", ppp, 1, N);      bd.place(3, 0)
        layout.connect(ad_out, bd_in)
        (kc_in, kc_out, kc)     = get_kvcore(layout, "dec_kvcore", ppp, N);         kc.place(5, 0)
        layout.connect(bd_out, kc_in)
        (mx_in, mx_out, mx)     = get_mux(layout, "dec_mux", 1, 1, N);              mx.place(7, 0)
        layout.connect(kc_out, mx_in)
        # --- decode PE (single PE): kv-partials in (<- mux), in (host), out (host) ---
        rg = layout.create_code_region(kernel_path, "dec", 1, 1); rg.place(9, 0)
        kv_c, in_c, out_c = rg.color("kv_color"), rg.color("in_color"), rg.color("out_color")
        for name in ("in_wlts", "south_wlts", "draft_len", "sampled_off"):
            rg.set_param_all(name, counts[name])
        rg.set_param_all("kv_pes", N)
        rg.set_param_all("kv_color", kv_c); rg.set_param_all("in_color", in_c); rg.set_param_all("out_color", out_c)
        rg.paint_all(kv_c,  [RoutingPosition().set_input([Route.WEST]).set_output([Route.RAMP])])
        rg.paint_all(in_c,  [RoutingPosition().set_input([Route.RAMP]).set_output([Route.RAMP])])
        rg.paint_all(out_c, [RoutingPosition().set_input([Route.RAMP]).set_output([Route.EAST])])
        kv_port = rg.create_input_port(kv_c, Edge.LEFT, [RoutingPosition().set_output([Route.RAMP])], N)
        in_port = rg.create_input_port(in_c, Edge.TOP,  [RoutingPosition().set_output([Route.RAMP])], counts["in_wlts"])
        out_port = rg.create_output_port(out_c, Edge.RIGHT, [RoutingPosition().set_input([Route.RAMP])], counts["south_wlts"], prefix="dec_out")
        layout.connect(mx_out, kv_port)   # on-chip: mux partials -> decode PE kv input
        return {"kv": layout.create_input_stream(kv_h2d_in),
                "in": layout.create_input_stream(in_port),
                "out": layout.create_output_stream(out_port)}
    return build_layout
```

Note the friction point resolved here: with `kv` now arriving from the WEST (mux) via `layout.connect`, the host `in`/`out` ports must use free edges — put `in` on `Edge.TOP` and `out` on `Edge.RIGHT` (the mux is on the LEFT). Resolve any routing collision against the compiler; keep the host interface (`{"kv","in","out"}`) identical so `DecodeAppliance` is untouched.

- [ ] **Step 4: Point `decode_sim_check.py` at the fanout config** — it already loads `config/v0_sim_pd.json` (now with `fanout_w/h`); the oracle (`expected_kv → kv_checksum → (ingress_i + cksum)`) is UNCHANGED. No test-logic change; just confirm it reads the multi-PE config and that `load_kv` still takes `kv_words`.

- [ ] **Step 5: Run the decode sim gate**

Run: `/home/lexu/Cerebras-SDK-2.10.0/cs_python waferengine/samples/specdec/decode_sim_check.py`
Expected: `DECODE_SIM_PASS` — the KV now enters via the 4-PE demux, each PE reduces its 224-word slice, the mux delivers 4 partials, the decode PE XORs them to the SAME `kv_cksum` and folds it. Bit-exact vs the host oracle proves the whole KV fanned onto the chip. Iterate CSL/placement in simfab until green.

- [ ] **Step 6: Commit**

```bash
git add waferengine/samples/specdec/kernel/fanout/kvcore.csl waferengine/samples/specdec/kernel/decode_pt.csl \
        waferengine/samples/specdec/fanout_layout.py waferengine/samples/specdec/appliance.py \
        waferengine/samples/specdec/decode_sim_check.py
git commit -m "feat(specdec): decode KV H2D is multi-PE (demux->kvcore reduce->mux->decode PE); DECODE_SIM_PASS (PD M4)"
```

---

### Task 4: Prefill multi-PE D2H — `pfcore.csl` + prefill PE rewrite + `_build_prefill` + gate

Fan the KV *emit* across the array: replicate the (small) prompt N times host-side; `adaptor→demux` hands each `pfcore` PE its own copy plus a slice base; each PE generates its contiguous `kv_words_per_pe` slice of the deterministic KV and emits it; `mux` collects the slices in PE order to the single `out` FPGA port; the host reassembles the exact `kv_words` blob.

**Files:**
- Create: `waferengine/samples/specdec/kernel/fanout/pfcore.csl` (derived from `buffer.csl`: generate-not-forward)
- Modify: `waferengine/samples/specdec/kernel/prefill_pt.csl` → superseded by `pfcore.csl` (the prefill PE array IS pfcore; there is no separate single prefill PE). Keep the file but mark it legacy, OR delete and update references. (Decision: **keep `prefill_pt.csl` deleted from the build path**; the multi-PE prefill has no single-PE region — its host I/O is the adaptor h2d + mux d2h.)
- Modify: `waferengine/samples/specdec/appliance.py` (`_build_prefill` rewrite + `PrefillAppliance.prefill` host-side replicate/reassemble)
- Modify: `waferengine/samples/specdec/prefill_sim_check.py` (fanout config; oracle unchanged)

**Interfaces:**
- Produces:
  - `pfcore.csl` params: `pe_batch: u16` (= `1 + in_wlts`, the per-PE input batch: `[slice_base, ingress...]`), `per_pe: u16` (= `kv_words_per_pe`), `in_color`, `out_color`. Reads `pe_batch` u32 (WEST→RAMP): `slice_base = inbuf[0]`, `ntok = inbuf[1]`, ids at `inbuf[2..]`; generates `per_pe` u32 `outbuf[m] = inbuf[2 + ((slice_base+m) % ntok)] + (slice_base+m)`; emits `per_pe` u32 (RAMP→EAST). (Index math mirrors `prefill_pt.csl`'s `inbuf[1 + (j % ntok)]`, shifted by the extra `slice_base` header slot → `inbuf[2 + ...]`.)
  - `get_pfcore(layout, name, pe_batch, per_pe, height)` builder in `fanout_layout.py` — like `get_buffer` but input-port per-PE width `pe_batch`, output-port per-PE width `per_pe`.
  - `_build_prefill(counts)` builds `get_demux_adaptor("pf_adaptor", pe_batch, N)`, `get_b_demux("pf_demux", pe_batch, 1, N)`, `get_pfcore(..., pe_batch, per_pe, N)`, `get_mux("pf_mux", per_pe, 1, N)`. Returns `{"in": <adaptor h2d stream>, "out": <mux d2h stream>}`.
  - `PrefillAppliance.prefill(ingress)` UNCHANGED SIGNATURE — internally builds the replicated `N*(1+in_wlts)` host buffer (`batch_k = [k*per_pe] + padded_ingress`) and sends it on `"in"`; receives `kv_words` on `"out"` (already in order → the KV blob). Returns `list[int]` of length `kv_words`, exactly as before.

- [ ] **Step 1: Write `pfcore.csl`** (ASCII-only; derived from `buffer.csl` + `prefill_pt.csl` fill):

```
// Derived from .../e3.5/buffer.csl + specdec/prefill_pt.csl. A 1xN strip PE that
// GENERATES its contiguous per_pe slice of the deterministic mock KV from a
// replicated prompt batch [slice_base, num_tokens, id0, id1, ...] and emits it
// east into the mux. mux collects slices in PE order -> host reassembles kv_words.
param pe_batch: u16;     // = 1 + in_wlts (slice_base + padded ingress)
param per_pe:   u16;     // = kv_words_per_pe (this PE's KV slice length)
param in_color:  u16;    // demux (WEST) -> RAMP
param out_color: u16;    // RAMP -> mux (EAST)

const input_q  = @get_input_queue(0);
const output_q = @get_output_queue(1);

var inbuf:  [pe_batch]u32 = @zeros([pe_batch]u32);
var outbuf: [per_pe]u32   = @zeros([per_pe]u32);

const in_mem_dsd  = @get_dsd(mem1d_dsd, .{ .base_address = &inbuf,  .extent = pe_batch });
const out_mem_dsd = @get_dsd(mem1d_dsd, .{ .base_address = &outbuf, .extent = per_pe });
const in_dsd  = @get_dsd(fabin_dsd,  .{ .extent = pe_batch, .fabric_color = @get_color(in_color),  .input_queue  = input_q });
const out_dsd = @get_dsd(fabout_dsd, .{ .extent = per_pe,   .fabric_color = @get_color(out_color), .output_queue = output_q });

const recv_id = @get_local_task_id(8);
const gen_id  = @get_local_task_id(9);
const send_id = @get_local_task_id(10);

task recv() void { @mov32(in_mem_dsd, in_dsd, .{ .async = true, .activate = gen_id }); }
task gen() void {
    var base: u32 = inbuf[0];
    var ntok: u16 = @as(u16, inbuf[1]);
    var m: u16 = 0;
    while (m < per_pe) : (m += 1) {
        var g: u32 = base + @as(u32, m);              // global KV index
        var idx: u16 = 2 + @as(u16, g % @as(u32, ntok));
        outbuf[@as(i16, m)] = inbuf[@as(i16, idx)] + g;
    }
    @activate(send_id);
}
task send() void { @mov32(out_dsd, out_mem_dsd, .{ .async = true, .activate = recv_id }); }

comptime {
    @bind_local_task(recv, recv_id);
    @bind_local_task(gen,  gen_id);
    @bind_local_task(send, send_id);
    @activate(recv_id);
    @initialize_queue(input_q, .{ .color = @get_color(in_color) });
    if (@is_arch("wse3")) { @initialize_queue(output_q, .{ .color = @get_color(out_color) }); }
}
```

(Iterate casts against `cslc` — `g % ntok` on mixed widths may need explicit `@as`; the acceptance is the gate. The oracle is `expected_kv`: word `g = prompt[g % ntok] + g`, with `prompt` at ingress index 1.. → `inbuf[2..]` after the slice_base header.)

- [ ] **Step 2: Rewrite `_build_prefill`** — replace the single-PE region with the `adaptor→demux→pfcore→mux` chain:

```python
def _build_prefill(counts, kernel_file=None):
    def build_layout(layout):
        from cerebras.sdk.runtime.sdkruntimepybind import (Edge, Route, RoutingPosition)  # noqa: PLC0415
        from waferengine.samples.specdec.fanout_layout import (  # noqa: PLC0415
            get_demux_adaptor, get_b_demux, get_pfcore, get_mux)
        N        = counts["fanout_pes"]
        per_pe   = counts["kv_words_per_pe"]
        pe_batch = 1 + counts["in_wlts"]
        (h2d_in, ad_out, ad) = get_demux_adaptor(layout, "pf_adaptor", pe_batch, N); ad.place(1, 0)
        (bd_in, bd_out, bd)  = get_b_demux(layout, "pf_demux", pe_batch, 1, N);      bd.place(3, 0)
        layout.connect(ad_out, bd_in)
        (pc_in, pc_out, pc)  = get_pfcore(layout, "pf_core", pe_batch, per_pe, N);   pc.place(5, 0)
        pc.set_param_all("pe_batch", pe_batch); pc.set_param_all("per_pe", per_pe)
        layout.connect(bd_out, pc_in)
        (mx_in, d2h_out, mx) = get_mux(layout, "pf_mux", per_pe, 1, N);              mx.place(7, 0)
        layout.connect(pc_out, mx_in)
        return {"in": layout.create_input_stream(h2d_in),
                "out": layout.create_output_stream(d2h_out)}
    return build_layout
```

(`get_pfcore` sets `in_color`/`out_color` like `get_buffer`; `pe_batch`/`per_pe` are set here or inside the builder — keep consistent with how `get_buffer` sets `pe_length`.)

- [ ] **Step 3: Rewrite `PrefillAppliance.prefill`** — replicate host-side, reassemble is a no-op (mux is in order):

```python
    def prefill(self, u32s):
        c = self._counts
        assert len(u32s) <= c["in_wlts"], "prefill ingress exceeds in_wlts"
        padded = list(u32s) + [0] * (c["in_wlts"] - len(u32s))
        N, per_pe = c["fanout_pes"], c["kv_words_per_pe"]
        batch = []
        for k in range(N):
            batch += [k * per_pe] + padded          # [slice_base, ingress...] per PE
        self._sess.send(batch)                        # -> adaptor h2d ("in")
        return [int(x) for x in self._sess.receive(c["kv_words"])]   # <- mux d2h ("out")
```

- [ ] **Step 4: Run the prefill sim gate**

Run: `/home/lexu/Cerebras-SDK-2.10.0/cs_python waferengine/samples/specdec/prefill_sim_check.py`
Expected: `PREFILL_SIM_PASS` — 4 PEs each generate 224 KV words from their slice base; the mux reassembles the 896-word blob; bit-exact vs `codec.expected_kv([101,102,103,104], 896)`. Iterate CSL/placement until green.

- [ ] **Step 5: Commit**

```bash
git add waferengine/samples/specdec/kernel/fanout/pfcore.csl waferengine/samples/specdec/fanout_layout.py \
        waferengine/samples/specdec/appliance.py waferengine/samples/specdec/prefill_sim_check.py \
        waferengine/samples/specdec/kernel/prefill_pt.csl
git commit -m "feat(specdec): prefill KV D2H is multi-PE (replicated prompt->demux->pfcore gen->mux); PREFILL_SIM_PASS (PD M4)"
```

---

### Task 5: PD capstone sim gate (two processes, KV over loopback) + retire the pad hack

Prove the full disaggregation with BOTH sides multi-PE, over the UNCHANGED disk-free `kv_channel` (loopback), bit-exact vs the host oracle. Confirm the transport is untouched and the real `kv_words` now traverses the chip on both ends.

**Files:**
- Reuse: `waferengine/samples/specdec/pd_worker.py` + `pd_sim_check.py` — they call `PrefillAppliance.prefill`/`DecodeAppliance.load_kv`/`exchange_batch` with UNCHANGED signatures, so they need **no edits**. The multi-PE build is transparent to them.
- Modify: `waferengine/samples/specdec/appliance_handlers.py` — remove the now-obsolete `IOP_KV_XFER_BYTES` zero-pad path in `build_prefill_handlers`/`_receive_and_load` (the real `kv_words` now enters/exits the chip; the pad hack that decoupled transport-size from single-PE kernel-size is no longer needed). Keep `kv_bytes(cfg)` as the transport size. (Do this as a small, tested edit; leave `warm(xfer_bytes)` using `kv_bytes` directly.)
- Test: add `tests/test_handlers_no_pad.py` asserting the prefill handler sends exactly `kv_bytes(cfg)` (no `IOP_KV_XFER_BYTES` inflation) with a fake sender.

**Interfaces:**
- Produces: `PD_SIM_PASS` from `pd_sim_check.py` with the multi-PE config — prefill (proc A) fans its KV out through the mux → `kv_channel` loopback → decode (proc B) fans it back in through the demux → decode output reflects the exact prompt-derived checksum. One fabric per process honored (two processes).

- [ ] **Step 1: Write the failing handler test** — `tests/test_handlers_no_pad.py`:

```python
import numpy as np
from waferengine.samples.specdec import appliance_handlers as H
from waferengine.samples.specdec import codec

class _FakeApp:
    def __init__(self, counts): self.c = counts
    def prefill(self, ingress): return list(range(self.c["kv_words"]))
class _FakeSender:
    def __init__(self): self.sent = []
    def send(self, sid, buf): self.sent.append(buf)

def test_prefill_handler_sends_exact_kv_bytes(monkeypatch):
    cfg = {"draft_len": 16, "bsz": 1, "top_k": 8, "n_layers": 7, "n_kv_heads": 2,
           "head_dim": 16, "kv_dtype_bytes": 2, "prefill_len": 4, "fanout_w": 2, "fanout_h": 2}
    monkeypatch.setenv("IOP_KV_XFER_BYTES", "999999")   # must be IGNORED now
    s = _FakeSender()
    h = H.build_prefill_handlers(cfg, appliance_factory=lambda c: _FakeApp(c),
                                 sender_factory=lambda: s, session="t")
    h[list(h)[0]](codec.encode_request_payload(has_commit=True, has_proposal=True,
                  num_accepted=2, correction_ids=[1, 2, 3]))
    assert len(s.sent[0]) == codec.kv_bytes(cfg)
```

- [ ] **Step 2: Run to verify it fails** — Run: `python3 -m pytest waferengine/samples/specdec/tests/test_handlers_no_pad.py -v` → FAIL (still pads to 999999).

- [ ] **Step 3: Remove the pad path** in `appliance_handlers.py`: drop `_xfer_bytes` inflation and the `buf + b"\x00"*(...)` pad in `exch`; `_receive_and_load` drops the `raw[:kv_nbytes]` truncation guard's *reason* (still safe to keep the slice, but the surplus no longer exists). Update the docstrings that reference the "single-PE passthrough kernel (which still only emits/consumes the real kv_bytes)" — that limitation is GONE in M4. Keep `warm(kv_bytes(cfg))`.

- [ ] **Step 4: Run to verify pass + host suite green**

Run: `python3 -m pytest waferengine/samples/specdec/tests/ -q`
Expected: PASS (new test + all prior; any test asserting `IOP_KV_XFER_BYTES` behavior must be updated/removed as part of this task).

- [ ] **Step 5: Run the PD capstone sim gate**

Run: `python3 waferengine/samples/specdec/pd_sim_check.py`
Expected: `PD_SIM_PASS` — full multi-PE disaggregation over loopback `kv_channel`, decode output bit-exact vs the host KV oracle. (~3-6 min: two `cs_python` compiles.)

- [ ] **Step 6: Commit**

```bash
git add waferengine/samples/specdec/appliance_handlers.py waferengine/samples/specdec/tests/test_handlers_no_pad.py
git commit -m "feat(specdec): retire IOP_KV_XFER_BYTES pad (real kv_words now traverses the chip); PD_SIM_PASS multi-PE (PD M4)"
```

---

### Task 6: CS-3 device gate — actual-size KV, real H2D, chunked-overlap opportunity (runbook + PENDING)

Wire the fan-out knobs through the driver/runbook and document the CS-3 device gate. No device run happens on this box; this task lands the scaling wiring + the PENDING gate text (mirror the M2b/M3 gate blocks in `README.md`).

**Files:**
- Modify: `waferengine/samples/specdec/driver_main.py` — forward `IOP_FANOUT_W`/`IOP_FANOUT_H` (or a config path) into both role commands so the two runtimes agree on the array size (mirror the `IOP_KV_STREAMS`/`IOP_KV_BACKEND` forwarding from M-par).
- Modify: `waferengine/samples/specdec/run_e2e_pd.sh` — forward the fanout knobs; document a large-config CS-3 profile.
- Create: `waferengine/samples/specdec/config/v0_cs3_pd.json` — a CS-3 profile with actual-size dims and a large `fanout_w*fanout_h` sized so `kv_words_per_pe*4 <= ~48 KB` (per-PE SRAM budget). Example toward 8K-token Qwen3 (28 layers, 8 kv heads, head_dim 128, bf16, prefill_len scaled): pick dims + `fanout_w/h` so the per-PE slice fits (e.g. `kv_words_per_pe <= 12000`); the array width follows from `kv_words / kv_words_per_pe`.
- Modify: `README.md` — add the M4 section + PENDING device gate.

**Interfaces:**
- Produces: the runbook + `README.md` gate. No new runtime API.

- [ ] **Step 1: Driver + runbook wiring** — forward `IOP_FANOUT_W`/`IOP_FANOUT_H` from the driver env into both prefill and decode controller commands (guard: only append when set; no-role command byte-identical). Add a regression assertion in `tests/test_pd_driver.py` (both role commands carry the fanout env; no-role does not).

- [ ] **Step 2: CS-3 config** — write `config/v0_cs3_pd.json` with actual-size KV dims + a per-PE-budget-respecting `fanout_w/h`. Add a host-only test asserting `codec.kv_words_per_pe(cfg)*4 <= 49152` for that config (SRAM budget guard).

- [ ] **Step 3: README M4 section + PENDING device gate** — add:

  `> **PENDING (CS-3 device gate):** the multi-PE KV fan-out is not yet run on real wafers. Sim proves the full path (FANOUT_SIM_PASS / PREFILL_SIM_PASS / DECODE_SIM_PASS / PD_SIM_PASS) at toy size (fanout 2x2, kv_words=896). This gate needs two concurrent appliance allocations on CS-3 (cs3-runner skill) at ACTUAL-SIZE KV (config/v0_cs3_pd.json, ~896 MiB / 8K-token Qwen3) with fanout_w*fanout_h sized so each core PE's slice fits ~48 KB SRAM. It measures (a) the real on-chip H2D fan-out bandwidth (reference: e3.5 direct-link demux/mux achieved 8-11 GB/s H2D at >=128 MiB/stream per h2d_playground_overview.md) and (b) the chunked recv<->H2D overlap opportunity: because kv_channel delivers the KV in chunks (M-par N-stream) and the demux ingests per-batch, the H2D fan-out can overlap the network receive instead of the current recv-then-load serialization. Run: warm+async (IOP_KV_WARM=1, IOP_KV_LOAD=async) + IOP_FANOUT_W/H via run_e2e_pd.sh.`

- [ ] **Step 4: Commit**

```bash
git add waferengine/samples/specdec/driver_main.py waferengine/samples/specdec/run_e2e_pd.sh \
        waferengine/samples/specdec/config/v0_cs3_pd.json waferengine/samples/specdec/README.md \
        waferengine/samples/specdec/tests/test_pd_driver.py
git commit -m "feat(specdec): fanout_w/h driver+runbook wiring + CS-3 actual-size config + M4 device-gate PENDING (PD M4)"
```

---

## Self-Review

**Spec coverage (M4):** the single-PE KV cap is lifted by PORTING (not reinventing) the e3.5 demux/mux unit into `kernel/fanout/` + `fanout_layout.py` (Task 1, verbatim + attribution + the two mandatory edits: absolute paths, ASCII comments). Decode H2D fans the `kv` stream across an N-PE `kvcore` array that reduces slices, muxed on-chip into the decode PE (Task 3); prefill D2H generates KV slices across an N-PE `pfcore` array muxed to the `out` port (Task 4); `in`/`out` stay single-PE. Sizing is config-driven (`fanout_w/h`, `kv_words_per_pe`, Task 2) — tiny (2x2) in sim, scalable on CS-3. The oracle (`expected_kv`/`kv_checksum`) is UNCHANGED and stays bit-exact by XOR associativity (decode) and PE-ordered reassembly (prefill). The sim gate is two `cs_python` processes over disk-free loopback `kv_channel` (Task 5, `PD_SIM_PASS`), and the `IOP_KV_XFER_BYTES` pad hack is retired because the real `kv_words` now traverses the chip. CS-3 device gate (actual-size KV, real H2D bandwidth, chunked-overlap opportunity) is wired + documented PENDING (Task 6).

**Honest boundary:** everything runnable on this box (host tests + the four sim gates) is a gate; the actual-size KV + real fan-out bandwidth + the recv<->H2D overlap are the CS-3 gate (two wafers), matching the M2b/M3/M-par PENDING convention. CSL iteration ACCEPTANCE is the sim gate (M2a precedent) — the ported CSL + the two new kernels (kvcore/pfcore) are concrete starting points, not placeholders; the oracle is the exact spec.

**Two genuine integration frictions, resolved in-plan (not hidden):**
1. *Decode global checksum across a fanned KV.* The fold needs ONE global `kv_cksum` on the single decode PE, but the KV is split across N PEs. Resolved by reusing the mux VERBATIM as an on-chip fan-IN of N 1-word partial checksums; the decode PE XORs the N partials. XOR associativity keeps it bit-exact with zero oracle change. (Alternative rejected: routing the whole KV to the decode PE would re-impose the 48 KB cap.)
2. *Prefill needs the prompt on every core PE, but the demux SPLITS (doesn't broadcast).* Resolved by REPLICATING the (tiny) prompt N times host-side with a per-PE `slice_base` header, so the demux is reused VERBATIM (split of N identical-plus-base batches) and each PE generates its contiguous slice; the mux reassembles in PE order. (Alternative rejected: a true broadcast/dispatch tree — that's the e11 16x16 pattern, heavier and not the "cleanest unit" the task points at; noted as a deferred 2-D scaling option.)

**Open questions / risks flagged for the implementer:**
- **`layout.connect` region-to-region into a live kernel port.** e3.5 chains adaptor->demux->buffer->mux all via `layout.connect`, but the decode PE's kv input port also carries a kernel fabin queue. Task 1's `FANOUT_SIM_PASS` de-risks the connect+edge mechanics before the KV specialization; if connecting a mux output into a kernel's fabin port fights the router, fall back to a trailing `buffer`(1x1) shim between mux and decode PE (still on-chip, still N-fan-in) — resolve against the compiler.
- **`W x H` vs `1 x N`.** The e3.5 unit distributes VERTICALLY (1 column x N rows; DESIGN.md confirms W=1 suffices for bandwidth). This plan maps `fanout_w x fanout_h` to `N = product` on a `1 x N` strip — the faithful port. A true 2-D grid (the e11 `x16x16` reference) is a documented follow-on if a single column of N rows exhausts fabric height at actual-size N.
- **Per-PE SRAM budget at actual size.** `kvcore`/`pfcore`/`buffer` all buffer their full `kv_words_per_pe` slice (`*4` bytes) locally — must stay within ~48 KB/PE, so actual-size N is large (Task 6 config guard). A streaming reduce (`kvcore` XORs wavelets as they arrive, no full buffer) removes the decode-side buffer and is the recommended CS-3 memory mitigation — noted, not required for the sim gate.
- **Direct-link D2H (mux path) is intrinsically slow.** The h2d_playground measurements show direct-link (SdkLayout stream) D2H at only ~0.14-0.27 GB/s vs H2D ~8-11 GB/s at large sizes (memcpy D2H is ~54 GB/s but is a different framework). The M4 win is the DECODE H2D ingest (the milestone's stated goal: "a real actual-size H2D measurement"). The PREFILL D2H emit through the mux is functionally correct and unblocks actual-size, but its bandwidth is the known-slow direct-link D2H — the CS-3 gate should report it honestly and NOT expect H2D-class numbers; a memcpy-framework D2H is a separate future option. Task 6's PENDING text should note this asymmetry.
- **`get_mux` size convention.** e3.5 `get_mux` uses `size = batch_size * height` (width fixed at 1); bandwidth-test-parallel's copy uses `batch_size * width * height`. With `width=1` (the faithful vertical strip) both are identical — port the e3.5 form; do not introduce `width>1` without switching to the `*width*height` form.

**Type consistency:** `fanout_pes(cfg)->int`, `kv_words_per_pe(cfg)->int`, `get_demux_adaptor(layout,name,batch_size,num_batches)`, `get_b_demux/get_mux(layout,name,batch_size,width,height)`, `get_buffer/get_kvcore(layout,name,pe_length,height)`, `get_pfcore(layout,name,pe_batch,per_pe,height)`, all returning `(in_port, out_port, region)`. `_build_decode`/`_build_prefill` return `dict[str,stream]` (`{"kv","in","out"}` / `{"in","out"}`). Appliance PUBLIC interfaces (`prefill(ingress)->kv_words`, `load_kv(kv_words)`, `exchange_batch`) UNCHANGED. Consistent across Tasks 1-6.
</content>
</invoke>
