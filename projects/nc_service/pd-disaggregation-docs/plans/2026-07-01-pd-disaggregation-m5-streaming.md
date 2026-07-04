# PD Disaggregation — M5 (single-PE STREAMING of an actual-size KV) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax. CSL iteration ACCEPTANCE is always the sim gate — mirror M2a/M4: the host-mirrored oracle (`codec.expected_kv`/`kv_checksum`) is the source of truth; iterate the `.csl` in simfab until the gate is bit-exact.

**Goal:** Prove an **actual-size KV** (toward 8K-token Qwen3 ≈ **896 MiB**) can **enter and leave the chip in ONE build**, lifting M2a's single-PE ~48 KiB SRAM cap — **by STREAMING through one PE**, not by spreading a resident copy across a 2-D grid. The KV is **generated on the fly** (D2H emit) and **reduced on the fly** (H2D ingest), so the on-chip resident footprint is O(chunk) (a few KiB) regardless of total volume. Volume is bounded only by how long the PE loops, not by SRAM.

## Why the 2-D grid was SHELVED (the design decision, recorded)

The earlier M5 direction was a `C×R` PE grid (fan the single host stream out to ~23K PEs, each holding a `per_pe` KV slice, then gather). It was evaluated in depth (e3.5-primitive 2-level tree vs lifting e11's dispatch spine; the hybrid = e11 geometry + reduce/generate leaves was recommended). **We shelved it after two facts made it the wrong tool for THIS milestone:**

1. **The grid never adds host bandwidth.** `SdkLayout` binds **one PE per physical host FPGA port** — so *both* the 1×N column and the C×R grid cross the host boundary through **one PE, one stream**; the grid only fans out *on-chip*, after that single port. Host↔chip throughput is identical with or without a grid. For streamed transit the grid buys **zero**.
2. **The grid's only real value is on-chip RESIDENCY** — physically HOLDING 896 MiB on-wafer (896 MiB / ~48 KiB ≈ 19-23K PEs, which one PE cannot). That residency is the REAL decode-appliance constraint (the live kernel reads the KV cache every token and cannot regenerate it). **But that is the job of the actual spec-dec kernel that will REPLACE this passthrough build** — not of the mock transport proof. In the passthrough build the KV contents are mocked, generated/consumed on the fly, and never need to persist. So residency is out of scope here.

Therefore, for the passthrough transport proof, the 48 KiB single-PE cap is lifted the *cheap* way — **stream + fold, never hold the whole KV** — which needs no grid, no fan-out routing, no per-PE SRAM budgeting, and preserves the M4 appliance interfaces trivially. The grid work is **deferred, not deleted** — see the M6 note.

## Recommended approach — SINGLE-PE STREAMING (generate-on-emit / reduce-on-ingest)

- **D2H (prefill emit):** one PE receives the tiny prompt `[ntok, ids...]` once, then LOOPS: fill a `chunk_words` buffer with the deterministic mock KV `word g = prompt[g % ntok] + g` for `g in [base, base+chunk_words)`, `@mov32` it out, advance `base`, repeat `kv_chunks` times. Emits `kv_words = kv_chunks·chunk_words` total; resident SRAM = one `chunk_words` buffer (reused) + the tiny prompt. Host reassembles and compares to `codec.expected_kv`.
- **H2D (decode ingest):** one PE LOOPS: `@mov32`-in a `chunk_words` chunk of the KV stream, XOR-fold each word into `kv_cksum`, repeat `kv_chunks` times. Never buffers more than one chunk; then folds `kv_cksum` into every exchange's sampled-token slot (the M2a oracle, UNCHANGED). Host verifies via `codec.kv_checksum`.
- **Chunked loop with a `u32` counter** (not a single giant DSD): `kv_words` at actual size (234,881,024) overflows the `u16`/`i16` DSD-extent field (e11 hit the same 65535 cap and switched to a `u32` loop counter — README l.99-103). So the extent is `chunk_words` (≤ a safe DSD size, e.g. 4096) and a `u32 chunks_done` counter drives the loop to `kv_chunks`.

**CSL justification (why streaming is correct and sufficient):** SRAM caps *resident* data only; a `@mov32` fabout/fabin loop that regenerates/consumes a reused buffer streams unbounded volume with O(chunk) footprint — the exact pattern e11's `dispatch_pe` already uses to relay >65535-word streams via a `u32` counter. Because the single host port is the sole host↔chip bandwidth path either way, one streaming PE achieves the same actual-size transport a grid would, minus all the fan-out routing/color/residency complexity, and the mock KV (generated on the fly, XOR-associative on reduce) needs no persistence. The public appliance interfaces (`prefill(ingress)->kv_words`, `load_kv(kv_words)`, `exchange_batch`, `{"kv","in","out"}`) stay byte-identical, so `pd_worker`/`appliance_handlers`/`driver`/`rendezvous`/`.proto` are untouched.

## Target-896 MiB sizing arithmetic (computed)
```
kv_bytes = n_layers·2·n_kv_heads·head_dim·kv_dtype_bytes·prefill_len·bsz
         = 28·2·8·128·2·8192·1  (Qwen3: 28 layers, 8 KV heads, hd 128, bf16, 8K ctx)
         = 939,524,096 B = 896.0 MiB exactly           (= 7·2^27)
kv_words = kv_bytes / 4 = 234,881,024 u32               (= 7·2^25)

STREAMING params (no grid):
  chunk_words = 4096  ->  16 KiB reused buffer  (<< ~44 KiB usable of the 48 KiB PE SRAM)
  kv_chunks   = kv_words / chunk_words = 234,881,024 / 4096 = 57,344   (fits u32; loop count)
  resident footprint on the ONE emit/ingest PE = 16 KiB, INDEPENDENT of the 896 MiB total.

Fabric footprint: a handful of PEs (emit PE / ingest+exchange PE + host-port PEs) — trivial
vs WSE-3 762x1172. The bottleneck is the single host-port bandwidth x 896 MiB, not the fabric.
Host<->chip volume: 896 MiB @ single-port direct-link (~0.14-0.27 GB/s D2H, ~8-11 GB/s H2D)
  -> D2H emit ~55-110 min (SLOW, known direct-link limit); H2D ingest ~85-110 ms. Report honestly.
```
`codec` asserts `kv_words % chunk_words == 0` AND `chunk_words*4 ≤ SRAM budget` (guards below). No per-PE-count math — there is one PE.

**Tech Stack:** CSL (SDK 2.10), `cerebras.sdk.runtime.sdkruntimepybind` via `cs_python` simfab, Python 3 host, pytest for host-only pieces, `cs_python` for sim gates. Device gate is CS-3 (WSE-3) via the `cs3-runner` skill.

## Global Constraints

- **SdkLayout single-stream I/O (one PE per stream) — REQUIRED.** The layout uses `SdkLayout` with `layout.create_input_stream(port)` / `layout.create_output_stream(port)`, each binding ONE PE on one physical host port. No fan-out, no grid, no multi-PE demux/mux. Per appliance: **prefill = 1 input stream (`in`) + 1 output stream (`out`)**; **decode = 2 input streams (`kv`, `in`) + 1 output stream (`out`)** (each a single-PE SdkLayout stream to the one decode PE — the M2a `{"kv","in","out"}` contract, unchanged). Volume rides the single stream via the kernel's chunked `@mov32` loop, NOT via more ports.
- **Public appliance interfaces UNCHANGED.** `PrefillAppliance.prefill(ingress)->kv_words`, `DecodeAppliance.load_kv(kv_words)`, `exchange_batch`, and `{"kv","in","out"}` are byte-identical to M2a/M4, so `pd_worker.py`/`appliance_handlers.py`/`driver_main.py`/rendezvous/`.proto` need no edits. `kv_channel` (warm/async) UNCHANGED.
- **Oracle stays bit-exact & UNCHANGED.** `codec.expected_kv`/`codec.kv_checksum` are the source of truth. D2H: host compares the received blob to `expected_kv(prompt, kv_words)`. H2D: streaming XOR-fold is associative ⇒ `kv_cksum == kv_checksum(kv)`; the decode PE folds it into `outbuf[i·south_wlts + sampled_off] = inbuf[i] + kv_cksum` exactly as M2a.
- **Resident footprint is O(chunk), NOT O(kv_words).** The emit/ingest PE allocates only `chunk_words` u32 (+ the tiny prompt on emit). **Assert `kv_words % chunk_words == 0`** AND **`chunk_words*4 ≤ 49152`**. Loop count is a `u32` (`kv_chunks`), never a `u16` extent.
- **CSL rules (as M2a/M4):** `.csl` ASCII-only; `NORTH/SOUTH/EAST/WEST` are reserved (`Route.*` only); one fabric per process (PD capstone = two `cs_python` processes); task ids `≥8`; `create_code_region` paths ABSOLUTE (`ApplianceSession` chdirs before `build_layout`).
- **Sim gates** run via `/home/lexu/Cerebras-SDK-2.10.0/cs_python <gate>.py` and print a single `*_PASS` line. Host-only tests: `python3 -m pytest waferengine/samples/specdec/tests/ -q`.
- **Sim proves NOT-SRAM-BOUND.** Every kernel gate runs at BOTH a tiny size (`kv_words=896`, sanity) AND a size that **exceeds one PE's resident cap** (`kv_words=14336` = 57 KiB > 48 KiB, `chunk_words=512` ⇒ 28 chunks) — the latter is the load-bearing proof that streaming lifts the M2a cap without a grid. Actual 896 MiB is the CS-3 device gate (sim is too slow for 234M words).
- **`fanout_w`/`fanout_h` are IGNORED by the M5 streaming build** (they were the shelved grid knobs; leave them in configs for M4 back-compat). M5 uses `kv_chunk_words`.
- **Attribution:** the `u32`-counter chunk-loop pattern is credited to `e11-sdklayout-fanout/dispatch_pe.csl` in a header comment; the generate/reduce bodies are derived from the M2a `prefill_pt.csl`/`decode_pt.csl` fills.

---

### Task 1: Streaming chunk sizing in `codec.py` + config knob (host-only, pure stdlib)

Add the streaming chunk helpers + guards. No SDK. (Leave M4's `fanout_pes`/`kv_words_per_pe` in place, unused by M5.)

**Files:**
- Modify: `waferengine/samples/specdec/codec.py` (`kv_chunk_words`, `kv_chunks`, `assert_stream_fits`; extend `derive_counts`)
- Modify: `waferengine/samples/specdec/config/v0_sim_pd.json` (add `"kv_chunk_words": 224`)
- Test: extend `waferengine/samples/specdec/tests/test_kv_oracle.py`

**Interfaces:**
- `codec.kv_chunk_words(cfg) -> int` = `int(cfg.get("kv_chunk_words", kv_words(cfg)))` (default = whole KV in one chunk = M2a back-compat).
- `codec.kv_chunks(cfg) -> int` = `kv_words(cfg) // kv_chunk_words(cfg)`; **raises ValueError** if `kv_words % chunk != 0`.
- `codec.assert_stream_fits(cfg, *, pe_sram_bytes=49152) -> None` — raises `ValueError` unless `kv_words % chunk == 0` and `chunk*4 ≤ pe_sram_bytes`.
- `derive_counts` (inside the existing `kv_dim_keys` guard) also sets `counts["kv_chunk_words"]`, `counts["kv_chunks"]` and calls `assert_stream_fits(cfg)`.

- [ ] **Step 1: Write failing tests** — append to `tests/test_kv_oracle.py`:
```python
def test_chunk_sizing_and_counts():
    cfg = {"n_layers":7,"n_kv_heads":2,"head_dim":16,"kv_dtype_bytes":2,
           "prefill_len":4,"bsz":1,"kv_chunk_words":224,"draft_len":16,"top_k":8}
    assert codec.kv_words(cfg)==896
    assert codec.kv_chunk_words(cfg)==224 and codec.kv_chunks(cfg)==4
    c = codec.derive_counts(cfg)
    assert c["kv_chunk_words"]==224 and c["kv_chunks"]==4

def test_chunk_defaults_to_whole_kv():
    cfg = {"n_layers":7,"n_kv_heads":2,"head_dim":16,"kv_dtype_bytes":2,
           "prefill_len":4,"bsz":1}
    assert codec.kv_chunk_words(cfg)==codec.kv_words(cfg) and codec.kv_chunks(cfg)==1

def test_assert_stream_rejects_indivisible():
    import pytest
    cfg = {"n_layers":7,"n_kv_heads":2,"head_dim":16,"kv_dtype_bytes":2,
           "prefill_len":4,"bsz":1,"kv_chunk_words":300}  # 896 % 300 != 0
    with pytest.raises(ValueError): codec.assert_stream_fits(cfg)

def test_assert_stream_rejects_oversized_chunk():
    import pytest
    big = {"n_layers":7,"n_kv_heads":2,"head_dim":16,"kv_dtype_bytes":2,
           "prefill_len":64,"bsz":1,"kv_chunk_words":14336}  # 14336*4=57 KiB > 48 KiB
    with pytest.raises(ValueError): codec.assert_stream_fits(big)

def test_cs3_896mib_stream_fits():
    cfg = {"n_layers":28,"n_kv_heads":8,"head_dim":128,"kv_dtype_bytes":2,
           "prefill_len":8192,"bsz":1,"kv_chunk_words":4096,"draft_len":16,"top_k":8}
    assert codec.kv_words(cfg)==234_881_024
    assert codec.kv_chunks(cfg)==57_344
    codec.assert_stream_fits(cfg)   # 16 KiB chunk, divides evenly -> OK
```
- [ ] **Step 2: Run to verify FAIL** — `python3 -m pytest .../tests/test_kv_oracle.py -k "chunk or stream or cs3" -v` → FAIL (`no attribute kv_chunk_words`).
- [ ] **Step 3: Implement** in `codec.py`:
```python
def kv_chunk_words(cfg): return int(cfg.get("kv_chunk_words", kv_words(cfg)))
def kv_chunks(cfg):
    total, ch = kv_words(cfg), kv_chunk_words(cfg)
    if total % ch != 0:
        raise ValueError(f"kv_words={total} not divisible by kv_chunk_words={ch}")
    return total // ch
def assert_stream_fits(cfg, *, pe_sram_bytes=49152):
    ch = kv_chunk_words(cfg)
    if kv_words(cfg) % ch != 0:
        raise ValueError(f"kv_words={kv_words(cfg)} not divisible by chunk={ch}")
    if ch * 4 > pe_sram_bytes:
        raise ValueError(f"chunk_words={ch} = {ch*4} B > PE SRAM {pe_sram_bytes}")
```
In `derive_counts` (inside the `kv_dim_keys` block): `counts["kv_chunk_words"] = kv_chunk_words(cfg); counts["kv_chunks"] = kv_chunks(cfg); assert_stream_fits(cfg)`.
- [ ] **Step 4: Config** — add `"kv_chunk_words": 224` to `config/v0_sim_pd.json` (896/224 = 4 chunks).
- [ ] **Step 5: Run** `python3 -m pytest .../tests/test_kv_oracle.py -q` → PASS.
- [ ] **Step 6: Commit** `feat(specdec): codec streaming chunk sizing (kv_chunk_words/kv_chunks + assert_stream_fits) (PD M5)`

---

### Task 2: D2H streaming emit — `prefill_stream.csl` + `_build_prefill` + gate

One PE: receive prompt once, then loop-generate `kv_chunks` chunks of the deterministic mock KV and stream them out. Resident footprint = one `chunk_words` buffer. Proves actual-size-class D2H emit lifts the SRAM cap.

**Files:**
- Create: `waferengine/samples/specdec/kernel/prefill_stream.csl`
- Modify: `waferengine/samples/specdec/appliance.py` (`_build_prefill` → single-PE streaming region; `PrefillAppliance.prefill` sends the prompt once, receives `kv_words`)
- Modify: `waferengine/samples/specdec/prefill_sim_check.py` (add the large > 48 KiB size)

**Interfaces:**
- `prefill_stream.csl` params: `in_wlts: u16` (prompt ingress size), `chunk_words: u16`, `kv_chunks: u32`, `in_color: u16`, `out_color: u16`. Reads `in_wlts` u32 (`[num_tokens, ids...]`) once; loops `kv_chunks` times generating `chunk_words` u32 per chunk from a running `base: u32`, emitting each chunk. Total emitted = `kv_chunks·chunk_words = kv_words`.
- `_build_prefill(counts)`: single 1×1 region; `set_param_all` `in_wlts, chunk_words, kv_chunks, in_color, out_color`; `in` host input (`Edge.LEFT`, size `in_wlts`), `out` host output (`Edge.RIGHT`, size `kv_words`). Returns `{"in": in_stream, "out": out_stream}`.
  - **NOTE (host receive size):** `PrefillAppliance.prefill` calls `self._sess.receive(kv_words)` — the host pulls `kv_words` u32 off the stream regardless of the kernel's per-chunk emit granularity, so the output stream is the flat `kv_words` blob in order. The chunked emit is invisible to the host contract.
- `PrefillAppliance.prefill(ingress)` UNCHANGED SIGNATURE — send `ingress` (`[num_tokens, ids...]`, padded to `in_wlts`) ONCE on `"in"`; `return [int(x) for x in self._sess.receive(counts["kv_words"])]`. (No replication, no reassembly — one PE emits the blob in order.)

- [ ] **Step 1: Write `prefill_stream.csl`** (ASCII; derived from M2a `prefill_pt.csl` fill + e11 `u32`-counter loop):
```
// Streaming D2H emit: one PE generates the deterministic mock KV on the fly and
// streams kv_chunks chunks out. Resident footprint = one chunk_words buffer.
// u32 chunk counter credited to e11 dispatch_pe.csl (>65535-word streams).
param in_wlts:     u16;   // prompt ingress [num_tokens, ids...]
param chunk_words: u16;   // words per streamed chunk (reused buffer size)
param kv_chunks:   u32;   // kv_words / chunk_words (loop count)
param in_color:    u16;
param out_color:   u16;

const IN: i16 = @as(i16, in_wlts);
var prompt: [IN]u32 = @zeros([IN]u32);
var buf:    [chunk_words]u32 = @zeros([chunk_words]u32);
var base: u32 = 0;
var done: u32 = 0;

const in_q:  input_queue  = @get_input_queue(2);
const out_q: output_queue = @get_output_queue(2);
const prompt_dsd = @get_dsd(mem1d_dsd, .{ .base_address = &prompt, .extent = IN });
const buf_dsd    = @get_dsd(mem1d_dsd, .{ .base_address = &buf, .extent = chunk_words });
const recv_dsd   = @get_dsd(fabin_dsd,  .{ .extent = IN,          .input_queue  = in_q });
const send_dsd   = @get_dsd(fabout_dsd, .{ .extent = chunk_words, .output_queue = out_q });

const recv_id = @get_local_task_id(8);
const gen_id  = @get_local_task_id(9);
const next_id = @get_local_task_id(10);

task recv() void { @mov32(prompt_dsd, recv_dsd, .{ .async = true, .activate = gen_id }); }
task gen() void {
    var ntok: u16 = @as(u16, prompt[0]);
    var m: u16 = 0;
    while (m < chunk_words) : (m += 1) {
        var g: u32 = base + @as(u32, m);
        var idx: u16 = 1 + @as(u16, g % @as(u32, ntok));   // prompt ids at [1..]
        buf[@as(i16, m)] = prompt[@as(i16, idx)] + g;
    }
    @mov32(send_dsd, buf_dsd, .{ .async = true, .activate = next_id });
}
task next() void {
    base += @as(u32, chunk_words);
    done += 1;
    if (done < kv_chunks) { @activate(gen_id); }   // else: all kv_words emitted
}
comptime {
    @bind_local_task(recv, recv_id);
    @bind_local_task(gen,  gen_id);
    @bind_local_task(next, next_id);
    @initialize_queue(in_q,  .{ .color = @get_color(in_color) });
    @initialize_queue(out_q, .{ .color = @get_color(out_color) });
    @activate(recv_id);
}
```
(Index math mirrors `codec.expected_kv`: `word g = prompt[g % ntok] + g`, ids at ingress `[1..]`. Iterate `%`/`@as` casts against `cslc`; the gate is acceptance.)
- [ ] **Step 2: Rewrite `_build_prefill`** — single 1×1 region (mirror the M2a `_build_passthrough` shape: `in` on `Edge.LEFT`→RAMP, `out` on `Edge.RIGHT`, RAMP→EAST), `set_param_all` the five params, `place(4,4)`. Rewrite `PrefillAppliance.prefill` to send-once/receive-`kv_words` (drop the M4 replicate loop).
- [ ] **Step 3: `prefill_sim_check.py`** — keep the tiny run (`v0_sim_pd.json`, kv_words=896, chunk 224) AND add a large run: a `config/v0_sim_pd_big.json` (`prefill_len=64` ⇒ kv_words=14336 > 48 KiB, `kv_chunk_words=512` ⇒ 28 chunks). Assert `kv == expected_kv(prompt, kv_words)` for BOTH. Print `PREFILL_STREAM_PASS`.
- [ ] **Step 4: Run** `/home/lexu/Cerebras-SDK-2.10.0/cs_python waferengine/samples/specdec/prefill_sim_check.py` → `PREFILL_STREAM_PASS`. The 14336-word run proves emit exceeds the single-PE resident cap while holding only a 2 KiB (512-word) buffer. Iterate in simfab until green.
- [ ] **Step 5: Commit** `feat(specdec): prefill D2H is single-PE streaming (generate-on-the-fly, O(chunk) SRAM); PREFILL_STREAM_PASS >48KiB (PD M5)`

---

### Task 3: H2D streaming ingest — `decode_stream.csl` + `_build_decode` + gate

One PE: loop-ingest `kv_chunks` chunks of the KV stream, XOR-fold each on the fly into `kv_cksum` (never buffering the whole KV), then fold `kv_cksum` into every exchange (M2a oracle). Proves actual-size-class H2D ingest lifts the SRAM cap.

**Files:**
- Create: `waferengine/samples/specdec/kernel/decode_stream.csl` (streaming-reduce variant of M2a `decode_pt.csl`)
- Modify: `waferengine/samples/specdec/appliance.py` (`_build_decode` → single-PE streaming region)
- Modify: `waferengine/samples/specdec/decode_sim_check.py` (add the large > 48 KiB size)

**Interfaces:**
- `decode_stream.csl` params: `in_wlts, south_wlts, draft_len, sampled_off: u16`, `chunk_words: u16`, `kv_chunks: u32`, `kv_color, in_color, out_color: u16`. The `kv` fabin reads `chunk_words` per iter; a `u32 done` counter loops `kv_chunks` times, XOR-folding each chunk into `kv_cksum`; when `done == kv_chunks`, `@activate(main_id)` starts the exchanges. Per-exchange `fill`/`done` and the `outbuf[i·south_wlts + sampled_off] = inbuf[i] + kv_cksum` oracle are UNCHANGED from M2a. **No `[kv_words]` buffer** — only `[chunk_words]`.
- `_build_decode(counts)`: single 1×1 region; `kv` host input (`Edge.LEFT`), `in` host input (`Edge.TOP`), `out` host output (`Edge.RIGHT`); `set_param_all` the params. Returns `{"kv","in","out"}`.
- `DecodeAppliance.load_kv(kv_list)` UNCHANGED — sends `kv_words` on `"kv"`; the kernel streams+folds it.

- [ ] **Step 1: Write `decode_stream.csl`** (ASCII; from M2a `decode_pt.csl`, swap the one-shot `[kv_words]` load for a chunked streaming reduce):
```
param in_wlts: u16; param south_wlts: u16; param draft_len: u16; param sampled_off: u16;
param chunk_words: u16; param kv_chunks: u32;
param kv_color: u16; param in_color: u16; param out_color: u16;

const IN: i16 = @as(i16, in_wlts);
const OUT_TOTAL: i16 = @as(i16, south_wlts) * @as(i16, draft_len);
var kvbuf:  [chunk_words]u32 = @zeros([chunk_words]u32);   // O(chunk), NOT O(kv_words)
var inbuf:  [IN]u32 = @zeros([IN]u32);
var outbuf: [OUT_TOTAL]u32 = @zeros([OUT_TOTAL]u32);
var kv_cksum: u32 = 0;
var done: u32 = 0;

const kv_q:  input_queue  = @get_input_queue(3);
const in_q:  input_queue  = @get_input_queue(2);
const out_q: output_queue = @get_output_queue(2);
const kv_recv_dsd = @get_dsd(fabin_dsd,  .{ .extent = chunk_words, .input_queue  = kv_q });
const recv_dsd    = @get_dsd(fabin_dsd,  .{ .extent = IN,          .input_queue  = in_q });
const send_dsd    = @get_dsd(fabout_dsd, .{ .extent = OUT_TOTAL,   .output_queue = out_q });
const kv_mem_dsd  = @get_dsd(mem1d_dsd,  .{ .base_address = &kvbuf,  .extent = chunk_words });
const in_mem_dsd  = @get_dsd(mem1d_dsd,  .{ .base_address = &inbuf,  .extent = IN });
const out_mem_dsd = @get_dsd(mem1d_dsd,  .{ .base_address = &outbuf, .extent = OUT_TOTAL });

const kvrecv_id = @get_local_task_id(8);
const kvfold_id = @get_local_task_id(9);
const main_id   = @get_local_task_id(10);
const fill_id   = @get_local_task_id(11);
const exdone_id = @get_local_task_id(12);

task kvrecv() void { @mov32(kv_mem_dsd, kv_recv_dsd, .{ .async = true, .activate = kvfold_id }); }
task kvfold() void {
    var j: u16 = 0;
    while (j < chunk_words) : (j += 1) { kv_cksum = kv_cksum ^ kvbuf[@as(i16, j)]; }
    done += 1;
    if (done < kv_chunks) { @activate(kvrecv_id); } else { @activate(main_id); }
}
task main() void { @mov32(in_mem_dsd, recv_dsd, .{ .async = true, .activate = fill_id }); }
task fill() void {
    var i: u16 = 0;
    while (i < draft_len) : (i += 1) {
        outbuf[@as(i16,i)*@as(i16,south_wlts) + @as(i16,sampled_off)] = inbuf[i] + kv_cksum;
    }
    @mov32(send_dsd, out_mem_dsd, .{ .async = true, .activate = exdone_id });
}
task exdone() void { @activate(main_id); }   // re-arm for next exchange (NOT the KV load)
comptime {
    @bind_local_task(kvrecv, kvrecv_id); @bind_local_task(kvfold, kvfold_id);
    @bind_local_task(main, main_id); @bind_local_task(fill, fill_id);
    @bind_local_task(exdone, exdone_id);
    @initialize_queue(kv_q, .{ .color = @get_color(kv_color) });
    @initialize_queue(in_q, .{ .color = @get_color(in_color) });
    @initialize_queue(out_q,.{ .color = @get_color(out_color) });
    @activate(kvrecv_id);   // stream+fold the KV ONCE at init; exdone re-arms main, not kvrecv
}
```
- [ ] **Step 2: Rewrite `_build_decode`** — single 1×1 region (mirror M2a: `kv` `Edge.LEFT`→RAMP, `in` `Edge.TOP`→RAMP, `out` `Edge.RIGHT` RAMP→EAST), `set_param_all` the params, `place(4,4)`. Return `{"kv","in","out"}`.
- [ ] **Step 3: `decode_sim_check.py`** — keep the tiny run AND add the large run (`v0_sim_pd_big.json`, kv_words=14336, chunk 512). Assert each exchange's sampled slot `== ingress[i] + kv_checksum(known_kv)` for BOTH. Print `DECODE_STREAM_PASS`.
- [ ] **Step 4: Run** `/home/lexu/Cerebras-SDK-2.10.0/cs_python waferengine/samples/specdec/decode_sim_check.py` → `DECODE_STREAM_PASS`. The 14336-word run proves ingest+fold exceeds the single-PE resident cap while holding only a 2 KiB buffer. Iterate until green.
- [ ] **Step 5: Commit** `feat(specdec): decode H2D is single-PE streaming XOR-reduce (O(chunk) SRAM); DECODE_STREAM_PASS >48KiB (PD M5)`

---

### Task 4: PD capstone — two-process streaming at > 48 KiB (`PD_STREAM_PASS`)

Prove full disaggregation with BOTH sides streaming, over the UNCHANGED disk-free `kv_channel` loopback, at a KV that exceeds the single-PE resident cap — bit-exact vs the host oracle. This is the pre-device capstone; the public interfaces are unchanged so `pd_worker.py`/`appliance_handlers.py` need **no edits**.

**Files:**
- Reuse (NO edits): `pd_worker.py`, `appliance_handlers.py`.
- Modify: `pd_sim_check.py` — point it at `config/v0_sim_pd_big.json` (kv_words=14336 > 48 KiB) so the capstone exercises the actual-size-class streaming path; rename its pass line to `PD_STREAM_PASS`.
- Test: `tests/test_pd_stream_smoke.py` — host-only assert that `derive_counts(v0_sim_pd_big)` yields `kv_chunks*kv_chunk_words == kv_words` and `assert_stream_fits` passes AND `kv_words*4 > 49152` (i.e. the capstone genuinely exceeds one-PE residency).

- [ ] **Step 1: Write the host-only guard test** (as above) → run → PASS.
- [ ] **Step 2: Run the capstone** — `python3 waferengine/samples/specdec/pd_sim_check.py` → `PD_STREAM_PASS`: prefill (proc A) streams-generates 14336 KV words → `kv_channel` loopback → decode (proc B) streams-folds them → decode output bit-exact vs the host KV oracle. One fabric per process (two `cs_python` compiles). Proves a > 48 KiB KV traverses BOTH ends in one build with O(chunk) resident footprint — no grid.
- [ ] **Step 3: Commit** `feat(specdec): PD capstone streaming both sides >48KiB over loopback kv_channel; PD_STREAM_PASS (PD M5)`

---

### Task 5: CS-3 device gate — actual-size 896 MiB streaming + runbook wiring + PENDING

Wire the chunk knob through the driver/runbook and land the actual-size config + PENDING device-gate text (no device run on this box).

**Files:**
- Create: `waferengine/samples/specdec/config/v0_cs3_pd.json` — the 896 MiB streaming profile:
  ```json
  {"draft_len":16,"bsz":1,"top_k":8,
   "n_layers":28,"n_kv_heads":8,"head_dim":128,"kv_dtype_bytes":2,"prefill_len":8192,
   "kv_chunk_words":4096}
  ```
  (kv_words=234,881,024; kv_chunks=57,344; 16 KiB resident buffer; runs on ONE PE.)
- Modify: `driver_main.py` + `run_e2e_pd.sh` — forward `IOP_KV_CHUNK_WORDS` into BOTH role commands (guard: only append when set; no-role command byte-identical). Add a regression assertion in `tests/test_pd_driver.py`.
- Modify: `README.md` — M5 section + PENDING device gate.

- [ ] **Step 1: Driver + runbook wiring** — forward `IOP_KV_CHUNK_WORDS`; regression test (both role commands carry it; no-role does not).
- [ ] **Step 2: CS-3 config + guard** — write `config/v0_cs3_pd.json`; host-only test asserting `codec.assert_stream_fits(cfg)` passes AND `kv_chunk_words(cfg)*4 == 16384` and `kv_chunks(cfg)==57344`.
- [ ] **Step 3: README M5 section + PENDING gate** — add:
  `> **PENDING (CS-3 device gate):** actual-size streaming is not yet run on real wafers. Sim proves the full path (PREFILL_STREAM_PASS / DECODE_STREAM_PASS / PD_STREAM_PASS) at >48 KiB (kv_words=14336, 2 KiB resident buffer) — i.e. beyond the single-PE M2a cap, without a grid. This gate runs the ACTUAL-SIZE KV (config/v0_cs3_pd.json, 896 MiB / 8K-token Qwen3, kv_words=234,881,024, kv_chunk_words=4096 => 57,344 chunks, 16 KiB resident on ONE PE) via the cs3-runner skill. It measures the single-host-port streaming bandwidth: H2D ingest (fold) ~8-11 GB/s reference (~85-110 ms) and D2H emit ~0.14-0.27 GB/s direct-link (~55-110 min -- SLOW, an inherent single-port direct-link limit, reported honestly, NOT improved by any grid). Drive via run_e2e_pd.sh with IOP_KV_WARM=1, IOP_KV_LOAD=async, IOP_KV_CHUNK_WORDS=4096.`
- [ ] **Step 4: Commit** `feat(specdec): kv_chunk_words driver+runbook wiring + CS-3 896MiB streaming config + M5 device-gate PENDING (PD M5)`

---

## Deferred — M6 (NOT this session): resident, distributed KV via the 2-D grid

The shelved 2-D grid work is deferred here, not deleted. **M6** wires a **resident** actual-size KV across the fabric — required by the LIVE spec-dec kernel that will REPLACE this passthrough build (the decode appliance must HOLD the KV cache on-wafer to read it every token; 896 MiB / ~48 KiB ≈ 19-23K PEs, impossible on one PE). The recommended vehicle (from the shelved analysis) is a **hybrid: e11's proven single-stream dispatch-spine 2-D tiling** (`build_supercolumn`, S=1: one vertical `dispatch_pe` spine + R horizontal rows — the only single-host-port topology that tiles without a color explosion or long routes) **with reduce/generate leaf bodies** and `dispatch_pe` parameterized by `IN_TILE`/`OUT_TILE`. The one open CSL risk recorded for M6: the decode reduce returns 1 word/PE while ingesting `per_pe`, so `dispatch_pe`'s output-phase DSD extents must be `OUT_TILE`-parameterized or the gather deadlocks — caught at a 2×2 grid gate before scale-up. M6 also owns any live-PD wiring beyond M5's interfaces. **None of M6 is in scope for M5.**

---

## Self-Review

**Scope decision (headline):** M5 is a **transport proof via single-PE streaming**, not a residency/distribution proof. The 2-D grid was shelved after establishing two facts: (1) `SdkLayout` binds one PE per host port, so a grid never adds host↔chip bandwidth — it only fans out on-chip; (2) the grid's sole value is on-chip RESIDENCY, which belongs to the real spec-dec kernel that will replace this passthrough, not to the mock. For the mock (KV generated/consumed on the fly, XOR-associative reduce), the M2a 48 KiB single-PE cap is lifted the cheap way: stream + fold with an O(chunk) reused buffer and a `u32` loop counter (the e11 `dispatch_pe` pattern). Public appliance interfaces stay byte-identical, so the whole PD pipeline runs unchanged.

**Spec coverage (M5):** codec gains `kv_chunk_words`/`kv_chunks` + `assert_stream_fits` guards (Task 1). D2H emit streams-generates the deterministic KV on one PE (`prefill_stream.csl`, `PREFILL_STREAM_PASS`, Task 2); H2D ingest streams-XOR-folds on one PE (`decode_stream.csl`, `DECODE_STREAM_PASS`, Task 3) — both bit-exact vs the UNCHANGED `expected_kv`/`kv_checksum` oracle, both gated at a size (14336 words = 57 KiB) that EXCEEDS the single-PE resident cap while holding only a 2 KiB buffer (the load-bearing not-SRAM-bound proof). The two-process capstone runs both streaming ends over the disk-free `kv_channel` loopback at >48 KiB (`PD_STREAM_PASS`, Task 4). CS-3 actual-size 896 MiB config (57,344 chunks, 16 KiB resident) + `IOP_KV_CHUNK_WORDS` wiring + PENDING device gate (Task 5). The shelved grid is deferred to M6.

**Honest boundaries / risks flagged for the implementer:**
- **D2H emit is intrinsically slow** at single-port direct-link (~0.14-0.27 GB/s ⇒ ~1 hr for 896 MiB). This is a host-port limit a grid would NOT fix (same single port). The device gate must report it honestly, not expect H2D-class numbers.
- **`u16` DSD extent, `u32` loop count.** `kv_words`=234M overflows a `u16`/`i16` extent — hence `chunk_words` (≤ a safe DSD size) as the extent and a `u32` counter (`kv_chunks`) driving the loop. Do NOT try a single kv_words-extent DSD.
- **Streaming reduce keeps NO whole-KV buffer.** `decode_stream.csl` allocates only `[chunk_words]`; if a refactor reintroduces a `[kv_words]` buffer the SRAM cap returns. `assert_stream_fits` guards the chunk, not a total.
- **`%`/`@as` casts** in the generate index math (`g % ntok` on mixed widths) may need explicit `@as` — the sim gate is the acceptance, iterate in simfab.
- **Sim can't run 896 MiB** (234M words is far too slow in simfab) — the actual size is the CS-3 device gate; sim proves correctness + not-SRAM-bound at 14336 words.

**Type consistency:** `kv_chunk_words(cfg)->int`, `kv_chunks(cfg)->int`, `assert_stream_fits(cfg,...)->None`. Kernels: `prefill_stream.csl`(in `in_wlts`, loop `kv_chunks`×`chunk_words` out), `decode_stream.csl`(loop `kv_chunks`×`chunk_words` fold, then M2a exchanges). `_build_prefill`->`{"in","out"}`, `_build_decode`->`{"kv","in","out"}`. Public `prefill(ingress)->kv_words`, `load_kv(kv_words)`, `exchange_batch` UNCHANGED. Consistent across Tasks 1-5.
