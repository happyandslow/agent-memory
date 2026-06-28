# PE SRAM Memory-Breakdown Tool — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a repeatable tool that turns a compiled CSL artifact into a per-PE 48 KB SRAM breakdown (code / weights / KV / activations / system / free) with a fabric heatmap and per-role stacked plots.

**Architecture:** A small Python package `pe_mem/` of pure, separately-testable parsers (`readelf` section + symbol parsing, `cs_readelf -m` per-coordinate totals, `sim.map` region boxes) feeding a categorizer and a matplotlib renderer, wired by a `run_breakdown.py` CLI. Built and unit-tested offline against the existing format-identical simulator artifacts (`out_perfunc/`, `out_s47/`); the authoritative device numbers come from a CS-3 compile whose artifact is pulled back and fed to the same pipeline.

**Tech Stack:** Python 3, matplotlib, GNU binutils (`readelf`, `size`), Cerebras `cs_readelf` (SIF wrapper at `/home/lexu/Cerebras-SDK-2.10.0/cs_readelf`), pytest.

## Global Constraints

- Tool home: `/home/lexu/WaferEngine/tools/pe_mem_breakdown/` (all paths below are relative to it unless absolute).
- Per-PE SRAM budget is **49152 bytes (48 KB)** — single source of truth constant `SRAM_BUDGET_BYTES = 49152`.
- Six categories, exact names: `code`, `weights`, `kv_cache`, `activations`, `system`, `free`. `rope` is reported as a labeled sub-total of `weights`, not a 7th top-level slice.
- **Attribution is symbol-driven** for `weights`/`kv_cache`/`activations` (they all live inside `.bss`); `code = .text`; `system = total − code − attributed_data_symbols`; `free = SRAM_BUDGET_BYTES − total`.
- Authoritative `total` per coordinate comes from `cs_readelf -m`; reconciliation `code + weights + kv_cache + activations + system == total` must hold within ±2 bytes/PE or it's a hard error.
- `cs_readelf` is a SIF wrapper (slow, ~10-30 s/call) — call it **once per artifact** on the combined `sim.elf`, never per-ELF in a loop.
- Never present simulator numbers as device numbers — every output records the source artifact dir and its fabric dims.
- Auto-commit after each task (user standing preference); commit only files under the tool dir; never push.
- Symbol byte sizes come from `readelf -sW` column 3 (already bytes — no element-size math needed).

---

### Task 1: Package skeleton + budget constant

**Files:**
- Create: `pe_mem/__init__.py`
- Create: `pe_mem/constants.py`
- Create: `tests/__init__.py`
- Create: `tests/test_constants.py`
- Create: `README.md` (stub)

**Interfaces:**
- Produces: `pe_mem.constants.SRAM_BUDGET_BYTES: int = 49152`, `pe_mem.constants.CATEGORIES: tuple[str,...] = ("code","weights","kv_cache","activations","system","free")`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_constants.py
from pe_mem.constants import SRAM_BUDGET_BYTES, CATEGORIES

def test_budget_is_48kb():
    assert SRAM_BUDGET_BYTES == 49152

def test_categories_exact():
    assert CATEGORIES == ("code", "weights", "kv_cache", "activations", "system", "free")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/lexu/WaferEngine/tools/pe_mem_breakdown && python -m pytest tests/test_constants.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pe_mem'`

- [ ] **Step 3: Write minimal implementation**

```python
# pe_mem/__init__.py
```
```python
# pe_mem/constants.py
SRAM_BUDGET_BYTES = 49152  # 48 KB per-PE SRAM on WSE-3
CATEGORIES = ("code", "weights", "kv_cache", "activations", "system", "free")
```
```python
# tests/__init__.py
```
```markdown
<!-- README.md -->
# PE SRAM Memory-Breakdown Tool
Per-PE SRAM breakdown (code/weights/KV/activations/system/free) for WaferEngine CSL artifacts.
See `/home/lexu/agent-memory/2026-06-28-pe-sram-memory-breakdown-tool-design.md` for the design.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_constants.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
cd /home/lexu/WaferEngine/tools/pe_mem_breakdown
git add pe_mem/ tests/ README.md
git commit -m "feat(pe_mem): package skeleton + SRAM budget/category constants"
```

---

### Task 2: ELF section + symbol parser (`readelf` wrapper)

**Files:**
- Create: `pe_mem/elf_parse.py`
- Create: `tests/test_elf_parse.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `parse_sections(readelf_S_text: str) -> dict[str, int]` — section name → byte size (allocated sections only: SHF_ALLOC, excludes `.debug*`, `.symtab`, `.strtab`, `.comment`, `.shstrtab`, `.note`).
  - `parse_symbols(readelf_s_text: str) -> list[tuple[str, int]]` — list of `(symbol_name, byte_size)` for `OBJECT` symbols with size > 0.
  - `elf_section_total(sections: dict[str,int]) -> int` — sum of allocated section bytes.
  - `read_elf(path: str) -> tuple[dict[str,int], list[tuple[str,int]]]` — runs `readelf -SW` and `readelf -sW` via subprocess, returns `(sections, symbols)`.

Parsing notes (from real output, decode-16.elf):
- `readelf -SW` rows look like `  [12] .text             PROGBITS        00000000 005818 005818 00  AX  0   0  4`. Field layout after `[NN]`: name, type, addr, off, **size(hex)**, ... — size is the 5th whitespace token after the name when split on the `]`. Robust approach: regex `^\s*\[\s*\d+\]\s+(\.\S+)\s+\S+\s+[0-9a-f]+\s+[0-9a-f]+\s+([0-9a-f]+)` → name, size(hex).
- Allocated sections to KEEP (contribute to SRAM): names starting with `.text`, `.data`, `.bss`, `.task_table`, `.fabric_routes`, `.fabric_switches`, `.entry_ival`, `.fpcw`, `.fscale`, `.blocked_ival`, `.active_ival`, `.blocked_ut_ival`, `.ce_in_q`, `.ce_out_q`, `.prng_state`, `.filters`, `.user_cfg_*`, `.csl_dcache`, `.cs.pe_state*`. EXCLUDE anything starting with `.debug`, `.note`, `.comment`, `.symtab`, `.strtab`, `.shstrtab`, `.pe_debug_info`. Implement as: keep if `not name.startswith(EXCLUDE_PREFIXES)`.
- `readelf -sW` rows: `   12: 0000105a   256 OBJECT  LOCAL  DEFAULT   18 UP_weight_tile`. Split on whitespace: index2 = size (decimal), index3 = type, last = name. Keep where type==`OBJECT` and size>0.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_elf_parse.py
from pe_mem.elf_parse import parse_sections, parse_symbols, elf_section_total

SEC_SAMPLE = """There are 40 section headers, starting at offset 0x7a40:
Section Headers:
  [Nr] Name              Type            Addr     Off    Size   ES Flg Lk Inf Al
  [ 0]                   NULL            00000000 000000 000000 00      0   0  0
  [ 1] .note             NOTE            00000000 007a40 000020 00      0   0  4
  [12] .text             PROGBITS        00000000 005818 005818 00  AX  0   0  4
  [13] .bss              NOBITS          0000102e 00102e 00102e 00  WA  0   0  4
  [14] .task_table       PROGBITS        00000000 000400 000400 00   A  0   0  4
  [15] .debug_info       PROGBITS        00000000 007d02 000736 00      0   0  1
"""

SYM_SAMPLE = """Symbol table '.symtab' contains 3 entries:
   Num:    Value  Size Type    Bind   Vis      Ndx Name
     1: 0000105a   256 OBJECT  LOCAL  DEFAULT   13 UP_weight_tile
     2: 00000fda    64 OBJECT  LOCAL  DEFAULT   13 XKCache_tile
     3: 00005818  1200 FUNC    LOCAL  DEFAULT   12 rmsnorm
"""

def test_parse_sections_keeps_allocated_excludes_debug():
    secs = parse_sections(SEC_SAMPLE)
    assert secs[".text"] == 0x5818
    assert secs[".bss"] == 0x102e
    assert secs[".task_table"] == 0x400
    assert ".debug_info" not in secs
    assert ".note" not in secs

def test_parse_symbols_objects_only():
    syms = parse_symbols(SYM_SAMPLE)
    assert ("UP_weight_tile", 256) in syms
    assert ("XKCache_tile", 64) in syms
    assert all(name != "rmsnorm" for name, _ in syms)  # FUNC excluded

def test_section_total_sums_allocated():
    secs = parse_sections(SEC_SAMPLE)
    assert elf_section_total(secs) == 0x5818 + 0x102e + 0x400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_elf_parse.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pe_mem.elf_parse'`

- [ ] **Step 3: Write minimal implementation**

```python
# pe_mem/elf_parse.py
import re
import subprocess

_EXCLUDE_PREFIXES = (".debug", ".note", ".comment", ".symtab", ".strtab",
                     ".shstrtab", ".pe_debug_info")
_SEC_RE = re.compile(
    r"^\s*\[\s*\d+\]\s+(\.\S+)\s+\S+\s+[0-9a-fA-F]+\s+[0-9a-fA-F]+\s+([0-9a-fA-F]+)")

def parse_sections(readelf_S_text: str) -> dict:
    out = {}
    for line in readelf_S_text.splitlines():
        m = _SEC_RE.match(line)
        if not m:
            continue
        name, size_hex = m.group(1), m.group(2)
        if name.startswith(_EXCLUDE_PREFIXES):
            continue
        out[name] = int(size_hex, 16)
    return out

def parse_symbols(readelf_s_text: str) -> list:
    out = []
    for line in readelf_s_text.splitlines():
        parts = line.split()
        if len(parts) < 8:
            continue
        # Num: Value Size Type Bind Vis Ndx Name
        if not parts[0].endswith(":"):
            continue
        try:
            size = int(parts[2])
        except ValueError:
            continue
        if parts[3] != "OBJECT" or size <= 0:
            continue
        out.append((parts[-1], size))
    return out

def elf_section_total(sections: dict) -> int:
    return sum(sections.values())

def read_elf(path: str):
    s_text = subprocess.run(["readelf", "-SW", path], capture_output=True,
                            text=True, check=True).stdout
    sym_text = subprocess.run(["readelf", "-sW", path], capture_output=True,
                              text=True, check=True).stdout
    return parse_sections(s_text), parse_symbols(sym_text)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_elf_parse.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Integration check against a real fixture**

Run: `python -c "from pe_mem.elf_parse import read_elf; s,y=read_elf('/home/lexu/WaferEngine/models/qwen3_1p7b-decode/out_perfunc/executables/decode-16.elf'); print(s.get('.text'), s.get('.bss')); print([t for t in y if 'weight' in t[0]][:3])"`
Expected: prints a `.text` size (~22552) and `.bss` (~4142) and a few `*weight_tile` symbols with byte sizes. (Sanity only; not a pytest gate.)

- [ ] **Step 6: Commit**

```bash
git add pe_mem/elf_parse.py tests/test_elf_parse.py
git commit -m "feat(pe_mem): readelf section + symbol parser"
```

---

### Task 3: `cs_readelf -m` per-coordinate parser

**Files:**
- Create: `pe_mem/cs_readelf.py`
- Create: `tests/test_cs_readelf.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `parse_msize(text: str) -> dict[tuple[int,int], int]` — `(x,y) -> total_bytes`.
  - `run_msize(artifact_dir: str, sif_wrapper: str = "/home/lexu/Cerebras-SDK-2.10.0/cs_readelf", elf_name: str = "sim.elf") -> dict[tuple[int,int], int]` — runs `cs_readelf -m <artifact_dir>/<elf_name>` once, returns the coordinate map.

Format (verified): lines like `(3, 9): 13872 bytes (6936 words)`. Header line `Memory used:` ignored.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cs_readelf.py
from pe_mem.cs_readelf import parse_msize

SAMPLE = """Memory used:
(0, 0): 5152 bytes (2576 words)
(3, 9): 13872 bytes (6936 words)
(2, 1): 1184 bytes (592 words)
"""

def test_parse_msize_coords():
    m = parse_msize(SAMPLE)
    assert m[(0, 0)] == 5152
    assert m[(3, 9)] == 13872
    assert m[(2, 1)] == 1184
    assert len(m) == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cs_readelf.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# pe_mem/cs_readelf.py
import os
import re
import subprocess

_LINE_RE = re.compile(r"^\((\d+),\s*(\d+)\):\s*(\d+)\s*bytes")

def parse_msize(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        m = _LINE_RE.match(line.strip())
        if m:
            out[(int(m.group(1)), int(m.group(2)))] = int(m.group(3))
    return out

def run_msize(artifact_dir: str,
              sif_wrapper: str = "/home/lexu/Cerebras-SDK-2.10.0/cs_readelf",
              elf_name: str = "sim.elf") -> dict:
    elf = os.path.join(artifact_dir, elf_name)
    res = subprocess.run([sif_wrapper, "-m", elf],
                         capture_output=True, text=True, check=True)
    return parse_msize(res.stdout)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_cs_readelf.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Integration check against real artifact**

Run: `python -c "from pe_mem.cs_readelf import run_msize; m=run_msize('/home/lexu/WaferEngine/models/qwen3_1p7b-decode/out_perfunc'); print(len(m), 'PEs'); print(sorted(set(m.values()))[:8])"`
Expected: prints a PE count and a small set of distinct totals (e.g. includes 1184, 3696, 5152, 13872). (Sanity only.)

- [ ] **Step 6: Commit**

```bash
git add pe_mem/cs_readelf.py tests/test_cs_readelf.py
git commit -m "feat(pe_mem): cs_readelf -m per-coordinate total parser"
```

---

### Task 4: `sim.map` region-box parser (coordinate → role)

**Files:**
- Create: `pe_mem/simmap.py`
- Create: `tests/test_simmap.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `parse_regions(simmap_text: str) -> dict[str, tuple[int,int,int,int]]` — region name → `(x0, x1, y0, y1)` inclusive-exclusive bounding box, parsed from region header lines (lines whose label has no `.` after the region name, i.e. `row_0.` not `row_0.UP_weight_tile`).
  - `coord_role(regions: dict, x: int, y: int) -> str | None` — return the region name containing `(x,y)`, or None.

Format (verified): region header line `row_0.<pad>[ y<8 x<18 <pad>] ( 0x0      9+x    1+y )`.
- The `[ y<H x<W ]` gives extents H (y count), W (x count).
- The `( 0xADDR  XEXPR  YEXPR )` gives origin: `XEXPR` like `9+x` → x0=9; `2` (constant) → x0=2, W from bracket. `YEXPR` like `1+y` → y0=1.
- So box = `(x0, x0+W, y0, y0+H)`. A region-header line is one where the token before `[` ends with exactly one `.` and nothing after it (no symbol). Detect: `label.endswith(".")` after stripping, OR `label.count(".")==1 and label.endswith(".")`.

Parsing recipe for one line:
1. Split off the label (everything before the first `[`).
2. `region = label.strip()`; treat as header iff `region.endswith(".")`.
3. From the `[ ... ]` block, regex `y<(\d+)` → H, `x<(\d+)` → W.
4. From the `( ... )` block, take the 2nd and 3rd whitespace tokens (XEXPR, YEXPR). `origin = lambda e: int(e.split("+")[0]) if "+" in e else int(e)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_simmap.py
from pe_mem.simmap import parse_regions, coord_role

SAMPLE = (
    "row_0.            [ y<8 x<18 ]    ( 0x0      9+x    1+y )\n"
    "ht_head.          [ y<8 x<6  ]    ( 0x0      3+x    1+y )\n"
    "x_demux.          [ y<8 x<1  ]    ( 0x0      2      1+y )\n"
    "row_0.UP_weight_tile [ y<8 x<18 n<128 ] ( 0x105a+n 9+x 1+y )\n"
)

def test_parse_regions_boxes():
    r = parse_regions(SAMPLE)
    assert r["row_0"] == (9, 27, 1, 9)      # x0=9,x1=9+18 ; y0=1,y1=1+8
    assert r["ht_head"] == (3, 9, 1, 9)
    assert r["x_demux"] == (2, 3, 1, 9)     # constant x origin 2, width 1
    assert "row_0.UP_weight_tile" not in r  # symbol line, not a region header

def test_coord_role_lookup():
    r = parse_regions(SAMPLE)
    assert coord_role(r, 9, 1) == "row_0"
    assert coord_role(r, 3, 5) == "ht_head"
    assert coord_role(r, 99, 99) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_simmap.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# pe_mem/simmap.py
import re

_Y_RE = re.compile(r"y<(\d+)")
_X_RE = re.compile(r"x<(\d+)")

def _origin(expr: str) -> int:
    return int(expr.split("+")[0]) if "+" in expr else int(expr)

def parse_regions(simmap_text: str) -> dict:
    regions = {}
    for line in simmap_text.splitlines():
        if "[" not in line or "(" not in line:
            continue
        label = line.split("[", 1)[0].strip()
        if not label.endswith("."):       # only region headers, not symbols
            continue
        region = label[:-1]
        bracket = line[line.index("[") + 1:line.index("]")]
        paren = line[line.rindex("(") + 1:line.rindex(")")]
        hy = _Y_RE.search(bracket)
        wx = _X_RE.search(bracket)
        if not (hy and wx):
            continue
        H, W = int(hy.group(1)), int(wx.group(1))
        toks = paren.split()
        # toks = [addr, XEXPR, YEXPR]
        x0, y0 = _origin(toks[1]), _origin(toks[2])
        regions[region] = (x0, x0 + W, y0, y0 + H)
    return regions

def coord_role(regions: dict, x: int, y: int):
    for name, (x0, x1, y0, y1) in regions.items():
        if x0 <= x < x1 and y0 <= y < y1:
            return name
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_simmap.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Integration check against real sim.map**

Run: `python -c "from pe_mem.simmap import parse_regions; r=parse_regions(open('/home/lexu/WaferEngine/models/qwen3_1p7b-decode/out_perfunc/sim.map').read()); import pprint; pprint.pprint(r)"`
Expected: prints boxes for `row_0`, `row_1`, `ht_head`, `ht_tail`, `x_demux`, `logits_mux`, `io_port_*`. (Sanity only.)

- [ ] **Step 6: Commit**

```bash
git add pe_mem/simmap.py tests/test_simmap.py
git commit -m "feat(pe_mem): sim.map region bounding-box parser"
```

---

### Task 5: Symbol/section categorizer

**Files:**
- Create: `pe_mem/categorize.py`
- Create: `tests/test_categorize.py`

**Interfaces:**
- Consumes: `pe_mem.constants.SRAM_BUDGET_BYTES`.
- Produces:
  - `categorize_symbol(name: str) -> str` — returns one of `weights`, `kv_cache`, `activations`, or `unclassified`. (RoPE symbols → `weights`.)
  - `is_rope(name: str) -> bool`.
  - `breakdown(sections: dict[str,int], symbols: list[tuple[str,int]], total: int) -> dict[str,int]` — returns a dict with keys `code, weights, kv_cache, activations, system, free, rope, unclassified` where:
    - `code = sections.get(".text", 0)`
    - `weights/kv_cache/activations` = summed symbol bytes by category; `rope` = subset of weights that are RoPE
    - `unclassified` = summed symbol bytes that matched no rule (also still added into one bucket? NO — kept separate and surfaced)
    - `system = total − code − weights − kv_cache − activations − unclassified`
    - `free = SRAM_BUDGET_BYTES − total`

Category rules (regex, case-sensitive, first match wins). Skip compiler-internal symbols whose name contains `csl_base_address` or starts with `__dsr_lowmeminit` — these are DSD/init slots → treat as `activations` (working-set scratch) so they don't pollute `unclassified`.

```
KV_CACHE  = r"(XKCache|XVCache|K_cache_bank|V_cache_bank|V_stash)"
ROPE      = r"(freqs_|^cos_|^sin_|delta_cos|delta_sin|cos_cur|sin_cur)"
WEIGHTS   = r"(_weight_tile|W_qkv_bank|W_o_bank|W_upgate_bank|W_down_bank|"
            r"_norm_tile|_norm_bank|q_norm|k_norm|lm_head|W_E_tile|"
            r"W_final_norm|we_buf|rms_w_)"
ACTIV     = r"(X_tile|X_input|X_norm|QKV|score|ffn_|z_upgate|z3|^h1$|^h2$|"
            r"Z_tile|Z_norm|^Z$|attn_|scratch_|_f32|local_|output_tile|"
            r"tap_|silu|embed_buf|token_id_buf|csl_base_address|__dsr_lowmeminit)"
```
Order of checks in `categorize_symbol`: KV_CACHE → WEIGHTS (rope falls under weights) → ACTIV → else `unclassified`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_categorize.py
from pe_mem.categorize import categorize_symbol, is_rope, breakdown

def test_symbol_categories():
    assert categorize_symbol("XKCache_tile") == "kv_cache"
    assert categorize_symbol("XVCache_tile") == "kv_cache"
    assert categorize_symbol("UP_weight_tile") == "weights"
    assert categorize_symbol("W_qkv_bank") == "weights"
    assert categorize_symbol("freqs_cos") == "weights"
    assert categorize_symbol("q_norm_tile") == "weights"
    assert categorize_symbol("QKV_f32") == "activations"
    assert categorize_symbol("score") == "activations"
    assert categorize_symbol("$$csl_base_address$$7$$ffn_up_gate_tile") == "activations"
    assert categorize_symbol("totally_unknown_xyz") == "unclassified"

def test_is_rope():
    assert is_rope("freqs_cos")
    assert is_rope("delta_sin_f32")
    assert not is_rope("UP_weight_tile")

def test_breakdown_reconciles():
    sections = {".text": 1000, ".bss": 500, ".task_table": 1024}
    symbols = [("UP_weight_tile", 256), ("XKCache_tile", 64), ("score", 40)]
    total = 1000 + 256 + 64 + 40 + 600  # code + weights + kv + act + 600 system
    b = breakdown(sections, symbols, total)
    assert b["code"] == 1000
    assert b["weights"] == 256
    assert b["kv_cache"] == 64
    assert b["activations"] == 40
    assert b["system"] == 600
    assert b["unclassified"] == 0
    # reconciliation identity (free excluded from the 'used' sum)
    assert b["code"] + b["weights"] + b["kv_cache"] + b["activations"] + b["system"] == total
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_categorize.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# pe_mem/categorize.py
import re
from pe_mem.constants import SRAM_BUDGET_BYTES

_KV = re.compile(r"(XKCache|XVCache|K_cache_bank|V_cache_bank|V_stash)")
_ROPE = re.compile(r"(freqs_|cos_|sin_|delta_cos|delta_sin)")
_WEIGHTS = re.compile(
    r"(_weight_tile|W_qkv_bank|W_o_bank|W_upgate_bank|W_down_bank|"
    r"_norm_tile|_norm_bank|q_norm|k_norm|lm_head|W_E_tile|W_final_norm|"
    r"we_buf|rms_w_)")
_ACTIV = re.compile(
    r"(X_tile|X_input|X_norm|QKV|score|ffn_|z_upgate|z3|h1|h2|"
    r"Z_tile|Z_norm|attn_|scratch_|_f32|local_|output_tile|"
    r"tap_|silu|embed_buf|token_id_buf|csl_base_address|__dsr_lowmeminit)")

def is_rope(name: str) -> bool:
    return bool(_ROPE.search(name)) and not bool(_WEIGHTS.search(name)) \
        or bool(re.search(r"(freqs_|delta_cos|delta_sin|cos_cur|sin_cur)", name))

def categorize_symbol(name: str) -> str:
    if _KV.search(name):
        return "kv_cache"
    if _WEIGHTS.search(name) or _ROPE.search(name):
        return "weights"
    if _ACTIV.search(name):
        return "activations"
    return "unclassified"

def breakdown(sections: dict, symbols: list, total: int) -> dict:
    code = sections.get(".text", 0)
    sums = {"weights": 0, "kv_cache": 0, "activations": 0, "unclassified": 0, "rope": 0}
    for name, size in symbols:
        cat = categorize_symbol(name)
        sums[cat] += size
        if cat == "weights" and is_rope(name):
            sums["rope"] += size
    system = total - code - sums["weights"] - sums["kv_cache"] \
        - sums["activations"] - sums["unclassified"]
    return {
        "code": code,
        "weights": sums["weights"],
        "kv_cache": sums["kv_cache"],
        "activations": sums["activations"],
        "system": system,
        "free": SRAM_BUDGET_BYTES - total,
        "rope": sums["rope"],
        "unclassified": sums["unclassified"],
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_categorize.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add pe_mem/categorize.py tests/test_categorize.py
git commit -m "feat(pe_mem): symbol-driven six-category classifier + reconciliation"
```

---

### Task 6: Extractor — artifact dir → per-coordinate categorized rows

**Files:**
- Create: `pe_mem/extract.py`
- Create: `tests/test_extract.py`

**Interfaces:**
- Consumes: `read_elf` (Task 2), `run_msize`/`parse_msize` (Task 3), `parse_regions`/`coord_role` (Task 4), `elf_section_total` (Task 2), `breakdown` (Task 5).
- Produces:
  - `match_coords_to_elf(coord_total: dict, elf_totals: dict, regions: dict, elf_region_of: dict) -> dict[tuple[int,int], str]` — assign each coordinate an ELF by: (a) restrict to ELFs whose region matches `coord_role`, (b) among those, pick the ELF whose section-total equals the coordinate total (exact, else nearest). Returns `(x,y) -> elf_basename`.
  - `extract_artifact(artifact_dir: str) -> list[dict]` — returns a list of row dicts, one per coordinate: `{"x","y","role","elf","total","code","weights","kv_cache","activations","system","free","rope","unclassified"}`. Uses real subprocess calls (integration-level).
  - `rows_to_csv(rows: list[dict], path: str) -> None`.
  - `elf_role(basename: str) -> str` — role from ELF name prefix (`decode-16.elf` → `decode`).

ELF→region mapping (`elf_region_of`): map the role prefix to sim.map region names. Decode ELFs (`decode-*`) cover regions `row_0`, `row_1`, … (all `row_*`); `ht_head-*`→`ht_head`; `ht_tail-*`→`ht_tail`; `demux-*`→`x_demux`; `mux-*`→`logits_mux`; `io_port-*`→`io_port_*`. Build this by: for each region name, role = region name with `row_*`→`decode`, `x_demux`→`demux`, `logits_mux`→`mux`, else the leading token. Then a coordinate's candidate ELFs are those whose role matches the coordinate's region-derived role.

- [ ] **Step 1: Write the failing test (pure join logic, no subprocess)**

```python
# tests/test_extract.py
from pe_mem.extract import match_coords_to_elf, elf_role

def test_elf_role():
    assert elf_role("decode-16.elf") == "decode"
    assert elf_role("ht_tail-17.elf") == "ht_tail"
    assert elf_role("io_port-9.elf") == "io_port"

def test_match_coords_by_region_and_total():
    # two decode ELFs with distinct totals; coord totals pick the right one
    coord_total = {(9, 1): 12694, (9, 2): 29246}
    elf_totals = {"decode-15.elf": 12694, "decode-16.elf": 29246,
                  "ht_head-13.elf": 3696}
    regions = {"row_0": (9, 27, 1, 9), "ht_head": (3, 9, 1, 9)}
    elf_region_of = {"decode-15.elf": "decode", "decode-16.elf": "decode",
                     "ht_head-13.elf": "ht_head"}
    m = match_coords_to_elf(coord_total, elf_totals, regions, elf_region_of)
    assert m[(9, 1)] == "decode-15.elf"
    assert m[(9, 2)] == "decode-16.elf"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_extract.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# pe_mem/extract.py
import csv
import glob
import os
from pe_mem.elf_parse import read_elf, elf_section_total
from pe_mem.cs_readelf import run_msize
from pe_mem.simmap import parse_regions, coord_role
from pe_mem.categorize import breakdown

def elf_role(basename: str) -> str:
    return basename.split("-")[0]

def _region_to_role(region: str) -> str:
    if region.startswith("row_"):
        return "decode"
    if region == "x_demux":
        return "demux"
    if region == "logits_mux":
        return "mux"
    if region.startswith("io_port"):
        return "io_port"
    return region  # ht_head, ht_tail

def match_coords_to_elf(coord_total, elf_totals, regions, elf_region_of):
    out = {}
    for (x, y), total in coord_total.items():
        region = coord_role(regions, x, y)
        if region is None:
            continue
        role = _region_to_role(region)
        cands = [e for e in elf_totals if elf_region_of.get(e) == role]
        if not cands:
            cands = list(elf_totals)
        best = min(cands, key=lambda e: abs(elf_totals[e] - total))
        out[(x, y)] = best
    return out

def extract_artifact(artifact_dir: str) -> list:
    coord_total = run_msize(artifact_dir)
    regions = parse_regions(open(os.path.join(artifact_dir, "sim.map")).read())
    elf_paths = sorted(glob.glob(os.path.join(artifact_dir, "executables", "*.elf")))
    sections_by_elf, symbols_by_elf, elf_totals, elf_region_of = {}, {}, {}, {}
    for p in elf_paths:
        b = os.path.basename(p)
        secs, syms = read_elf(p)
        sections_by_elf[b] = secs
        symbols_by_elf[b] = syms
        elf_totals[b] = elf_section_total(secs)
        elf_region_of[b] = elf_role(b)
    coord_elf = match_coords_to_elf(coord_total, elf_totals, regions, elf_region_of)
    rows = []
    for (x, y), total in sorted(coord_total.items()):
        region = coord_role(regions, x, y) or "?"
        elf = coord_elf.get((x, y))
        if elf is None:
            continue
        b = breakdown(sections_by_elf[elf], symbols_by_elf[elf], total)
        row = {"x": x, "y": y, "role": _region_to_role(region), "elf": elf,
               "total": total, **b}
        rows.append(row)
    return rows

def rows_to_csv(rows: list, path: str) -> None:
    if not rows:
        return
    fields = ["x", "y", "role", "elf", "total", "code", "weights", "kv_cache",
              "activations", "system", "free", "rope", "unclassified"]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r[k] for k in fields})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_extract.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Full-pipeline integration check + reconciliation against real sim artifact**

Run:
```bash
python -c "
from pe_mem.extract import extract_artifact
rows = extract_artifact('/home/lexu/WaferEngine/models/qwen3_1p7b-decode/out_perfunc')
print(len(rows), 'PEs')
bad = [r for r in rows if abs(r['code']+r['weights']+r['kv_cache']+r['activations']+r['system'] - r['total']) > 2]
print('reconciliation failures:', len(bad))
unc = [r for r in rows if r['unclassified'] > 0]
print('PEs with unclassified bytes:', len(unc))
import collections; print(collections.Counter(r['role'] for r in rows))
"
```
Expected: prints PE count, **`reconciliation failures: 0`**, the count of PEs with unclassified bytes (ideally 0; if >0, note which symbols — feed into extending the categorizer), and a role histogram. If reconciliation fails, fix the categorizer/section handling before proceeding — this is the correctness gate.

- [ ] **Step 6: Commit**

```bash
git add pe_mem/extract.py tests/test_extract.py
git commit -m "feat(pe_mem): artifact extractor with coord->ELF join + CSV output"
```

---

### Task 7: Renderer — heatmap + stacked + within-block + headroom

**Files:**
- Create: `pe_mem/plot.py`
- Create: `tests/test_plot.py`

**Interfaces:**
- Consumes: `pe_mem.constants.SRAM_BUDGET_BYTES, CATEGORIES`; CSV rows from Task 6.
- Produces:
  - `load_rows(csv_path: str) -> list[dict]` (ints parsed).
  - `role_summary(rows: list[dict]) -> dict[str, dict[str,float]]` — per role, mean bytes per category (data categories are PE-uniform; code/system averaged).
  - `max_seqlen_headroom(rows, bytes_per_token_per_pe: float) -> dict[str,float]` — min free among decode PEs → extra tokens (first-order; documented assumption).
  - `render(rows, out_prefix: str, kernel: str, bytes_per_token_per_pe: float) -> list[str]` — writes `<out_prefix>_heatmap.png`, `<out_prefix>_stacked.png`, `<out_prefix>_within_block.png`; returns the written paths.

Plot content:
- **heatmap.png**: two panels — `imshow`/scatter over (x,y) colored by `total` (left) and by `free/SRAM_BUDGET_BYTES` (right). Title includes kernel + artifact note. Use a fixed grid sized to max x,y.
- **stacked.png**: one stacked bar per role (x-axis), segments = the 5 used categories + free, drawn to `SRAM_BUDGET_BYTES`; horizontal line at the budget; legend; RoPE annotated as a hatch overlay on the weights segment or a printed sub-total in the table.
- **within_block.png**: for role `decode`, bar of min/median/max of `code` (and `total`) across distinct ELFs/coordinates → exposes central-vs-edge variation. If only one distinct decode total (e.g. on the uniform sim fixture), render a single bar and annotate "no intra-block variation in this artifact".

Test strategy: matplotlib in `Agg` backend; assert files are created and non-empty; assert `role_summary` and `max_seqlen_headroom` math on a tiny synthetic rowset.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_plot.py
import matplotlib
matplotlib.use("Agg")
import os
from pe_mem.plot import role_summary, max_seqlen_headroom, render

ROWS = [
    {"x":9,"y":1,"role":"decode","elf":"decode-15.elf","total":40000,
     "code":18000,"weights":20000,"kv_cache":200,"activations":800,
     "system":1000,"free":9152,"rope":64,"unclassified":0},
    {"x":9,"y":2,"role":"decode","elf":"decode-16.elf","total":40200,
     "code":18200,"weights":20000,"kv_cache":200,"activations":800,
     "system":1000,"free":8952,"rope":64,"unclassified":0},
]

def test_role_summary_means():
    s = role_summary(ROWS)
    assert s["decode"]["weights"] == 20000
    assert s["decode"]["code"] == 18100  # mean of 18000,18200

def test_headroom_tokens():
    # min free among decode = 8952 ; 80 bytes/token -> 111 extra tokens
    h = max_seqlen_headroom(ROWS, bytes_per_token_per_pe=80)
    assert h["min_free"] == 8952
    assert h["extra_tokens"] == 111  # floor(8952/80)

def test_render_writes_files(tmp_path):
    prefix = os.path.join(tmp_path, "decode")
    paths = render(ROWS, prefix, kernel="qwen3-decode", bytes_per_token_per_pe=80)
    assert len(paths) == 3
    for p in paths:
        assert os.path.exists(p) and os.path.getsize(p) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_plot.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# pe_mem/plot.py
import csv
import math
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pe_mem.constants import SRAM_BUDGET_BYTES

_USED = ["code", "weights", "kv_cache", "activations", "system"]
_INT_FIELDS = ["x", "y", "total", "code", "weights", "kv_cache",
               "activations", "system", "free", "rope", "unclassified"]

def load_rows(csv_path: str) -> list:
    rows = []
    with open(csv_path) as f:
        for r in csv.DictReader(f):
            for k in _INT_FIELDS:
                if k in r and r[k] != "":
                    r[k] = int(r[k])
            rows.append(r)
    return rows

def role_summary(rows: list) -> dict:
    by_role = {}
    for r in rows:
        by_role.setdefault(r["role"], []).append(r)
    out = {}
    for role, rs in by_role.items():
        out[role] = {c: sum(x[c] for x in rs) / len(rs)
                     for c in _USED + ["free", "rope"]}
    return out

def max_seqlen_headroom(rows: list, bytes_per_token_per_pe: float) -> dict:
    decode = [r for r in rows if r["role"] == "decode"]
    if not decode:
        return {"min_free": 0, "extra_tokens": 0}
    min_free = min(r["free"] for r in decode)
    return {"min_free": min_free,
            "extra_tokens": int(math.floor(min_free / bytes_per_token_per_pe))}

def render(rows: list, out_prefix: str, kernel: str,
           bytes_per_token_per_pe: float) -> list:
    paths = []

    # --- heatmap ---
    maxx = max(r["x"] for r in rows) + 1
    maxy = max(r["y"] for r in rows) + 1
    import numpy as np
    used = np.full((maxy, maxx), np.nan)
    freep = np.full((maxy, maxx), np.nan)
    for r in rows:
        used[r["y"], r["x"]] = r["total"]
        freep[r["y"], r["x"]] = 100.0 * r["free"] / SRAM_BUDGET_BYTES
    fig, axes = plt.subplots(1, 2, figsize=(14, 7))
    im0 = axes[0].imshow(used, origin="lower", aspect="auto")
    axes[0].set_title(f"{kernel}: total SRAM used (bytes)")
    fig.colorbar(im0, ax=axes[0])
    im1 = axes[1].imshow(freep, origin="lower", aspect="auto")
    axes[1].set_title(f"{kernel}: free %")
    fig.colorbar(im1, ax=axes[1])
    p = out_prefix + "_heatmap.png"; fig.savefig(p, dpi=110); plt.close(fig)
    paths.append(p)

    # --- stacked per role ---
    summ = role_summary(rows)
    roles = list(summ.keys())
    fig, ax = plt.subplots(figsize=(10, 7))
    bottom = [0.0] * len(roles)
    for cat in _USED + ["free"]:
        vals = [summ[role].get(cat, 0) for role in roles]
        ax.bar(roles, vals, bottom=bottom, label=cat)
        bottom = [b + v for b, v in zip(bottom, vals)]
    ax.axhline(SRAM_BUDGET_BYTES, color="k", ls="--", label="48 KB budget")
    ax.set_ylabel("bytes"); ax.set_title(f"{kernel}: per-role SRAM breakdown")
    ax.legend(loc="upper right", fontsize=8)
    p = out_prefix + "_stacked.png"; fig.savefig(p, dpi=110); plt.close(fig)
    paths.append(p)

    # --- within-block variation (decode) ---
    decode = [r for r in rows if r["role"] == "decode"]
    fig, ax = plt.subplots(figsize=(8, 6))
    if decode:
        codes = sorted(set(r["code"] for r in decode))
        totals = [r["total"] for r in decode]
        ax.bar(["code min", "code med", "code max"],
               [min(codes), codes[len(codes)//2], max(codes)])
        note = "no intra-block variation" if len(codes) == 1 else \
            f"code swing {max(codes)-min(codes)} B across {len(codes)} roles"
        ax.set_title(f"{kernel}: decode intra-block code variation\n{note}")
        ax.set_ylabel("bytes")
    p = out_prefix + "_within_block.png"; fig.savefig(p, dpi=110); plt.close(fig)
    paths.append(p)
    return paths
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_plot.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add pe_mem/plot.py tests/test_plot.py
git commit -m "feat(pe_mem): heatmap + stacked + within-block renderer"
```

---

### Task 8: CLI driver + bytes-per-token config

**Files:**
- Create: `run_breakdown.py`
- Create: `pe_mem/kv_cost.py`
- Create: `tests/test_kv_cost.py`

**Interfaces:**
- Consumes: `extract_artifact`, `rows_to_csv` (Task 6), `render`, `load_rows`, `max_seqlen_headroom` (Task 7).
- Produces:
  - `pe_mem.kv_cost.bytes_per_token_per_pe(model_config: dict) -> float` — first-order marginal KV bytes added per extra context token, per decode PE: `max_layers_per_block * 2 * kv_dim_per_pe * 2` (K+V, bf16=2B), where `max_layers_per_block = ceil(n_layers / n_blocks)`, `kv_dim_per_pe = kv_dim / P_BLOCK_SIZE`. Documented as a per-PE-turn first-order figure (KV is sharded by sequence position).
  - `run_breakdown.py` CLI: `--artifact DIR --kernel {decode,prefill} --config CONFIG.json --out OUTDIR [--sif PATH]` → writes `OUTDIR/<kernel>_breakdown.csv` + 3 PNGs + prints the per-role table and headroom line.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_kv_cost.py
from pe_mem.kv_cost import bytes_per_token_per_pe

def test_device_decode_kv_cost():
    cfg = {"n_layers": 28, "P_X_BLOCK_NUM": 2, "P_Y_BLOCK_NUM": 2,
           "kv_dim": 1024, "P_BLOCK_SIZE": 256}
    # max_layers_per_block = ceil(28/4)=7 ; kv_dim_per_pe = 1024/256 = 4
    # 7 * 2 * 4 * 2 = 112 bytes/token/PE
    assert bytes_per_token_per_pe(cfg) == 112
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_kv_cost.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# pe_mem/kv_cost.py
import math

def bytes_per_token_per_pe(model_config: dict) -> float:
    n_layers = model_config["n_layers"]
    n_blocks = model_config["P_X_BLOCK_NUM"] * model_config["P_Y_BLOCK_NUM"]
    max_layers_per_block = math.ceil(n_layers / n_blocks)
    kv_dim_per_pe = model_config["kv_dim"] // model_config["P_BLOCK_SIZE"]
    return max_layers_per_block * 2 * kv_dim_per_pe * 2  # K+V, bf16
```

```python
# run_breakdown.py
import argparse
import json
import os
from pe_mem.extract import extract_artifact, rows_to_csv
from pe_mem.plot import render, max_seqlen_headroom
from pe_mem.kv_cost import bytes_per_token_per_pe
from pe_mem.constants import SRAM_BUDGET_BYTES

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact", required=True)
    ap.add_argument("--kernel", required=True, choices=["decode", "prefill"])
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    cfg = json.load(open(args.config))
    rows = extract_artifact(args.artifact)
    csv_path = os.path.join(args.out, f"{args.kernel}_breakdown.csv")
    rows_to_csv(rows, csv_path)
    bpt = bytes_per_token_per_pe(cfg) if args.kernel == "decode" else float("nan")
    paths = render(rows, os.path.join(args.out, args.kernel),
                   kernel=f"qwen3-{args.kernel}", bytes_per_token_per_pe=bpt or 1)
    # summary table
    from pe_mem.plot import role_summary
    summ = role_summary(rows)
    print(f"\nArtifact: {args.artifact}  ({len(rows)} PEs)")
    print(f"{'role':10} {'code':>8} {'weights':>8} {'kv':>6} {'activ':>6} "
          f"{'system':>7} {'free':>7}  %used")
    for role, s in sorted(summ.items()):
        used = sum(s[c] for c in ["code","weights","kv_cache","activations","system"])
        print(f"{role:10} {s['code']:8.0f} {s['weights']:8.0f} {s['kv_cache']:6.0f} "
              f"{s['activations']:6.0f} {s['system']:7.0f} {s['free']:7.0f}"
              f"  {100*used/SRAM_BUDGET_BYTES:5.1f}%")
    if args.kernel == "decode":
        h = max_seqlen_headroom(rows, bpt)
        print(f"\nKV headroom (first-order): min free {h['min_free']} B / "
              f"{bpt:.0f} B-per-token => ~{h['extra_tokens']} extra context tokens")
    print("wrote:", csv_path, *paths)

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_kv_cost.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: End-to-end smoke run on the local sim artifact**

Run:
```bash
python run_breakdown.py \
  --artifact /home/lexu/WaferEngine/models/qwen3_1p7b-decode/out_perfunc \
  --kernel decode \
  --config /home/lexu/WaferEngine/models/qwen3_1p7b-decode/model_config/test_device_2x2blk.json \
  --out /tmp/pe_mem_out
```
Expected: prints a per-role table + headroom line; writes `decode_breakdown.csv` and 3 PNGs into `/tmp/pe_mem_out`. (Numbers are *simulator* numbers — clearly not device; that's expected for this smoke test.)

- [ ] **Step 6: Run the full test suite**

Run: `python -m pytest -v`
Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add run_breakdown.py pe_mem/kv_cost.py tests/test_kv_cost.py
git commit -m "feat(pe_mem): CLI driver + first-order KV-per-token headroom"
```

---

### Task 9: CS-3 device-compile + artifact-pull procedure

**Files:**
- Create: `compile_on_cs3.md` (documented procedure)
- Create: `pull_artifact.sh` (base64-over-ssh artifact retrieval)

**Interfaces:**
- Produces: a repeatable procedure to (a) compile the device config on CS-3 for the real `762,1172` fabric, (b) pull `executables/*.elf` + `sim.map` + `plan.json` to a local dir consumable by `run_breakdown.py`.

This task has **no unit test** — it is operational. It is gated by manual confirmation that the pulled artifact's `cs_readelf -m` shows the real device fabric (coordinates spanning the full placement, not the tight sim box) and that `run_breakdown.py` reconciles on it.

- [ ] **Step 1: Write the procedure doc**

`compile_on_cs3.md` content:
```markdown
# Device compile + artifact pull (authoritative numbers)

Compile-only is sufficient for memory numbers. Use the cs3-runner skill for
all cluster ops (honor OTP / ControlMaster rules in agent memory).

1. On CS-3, compile the device config (real fabric, live cmaddr):
   - decode:  cd models/qwen3_1p7b-decode  && ./run_device.sh   # or launch_device.py
   - prefill: cd models/qwen3_1p7b-prefill && ./run_device.sh
   The SdkLayout compile runs with --cmaddr=%CMADDR% so the artifact is sized
   for 762,1172. Note the artifact output dir it writes (e.g. out_device/).

2. Verify on CS-3 the artifact is device-sized:
   /home/lexu/Cerebras-SDK-2.10.0/cs_readelf -s <out_dir>/sim.elf   # fabric size
   -> must report the real fabric, not the tight sim box.

3. Pull the (small) artifact files only — NOT out.core / sim.elf if huge.
   We need: executables/*.elf, sim.map, plan.json. Use pull_artifact.sh.
   NOTE: cs_readelf -m needs sim.elf; if sim.elf is too large to pull,
   run `cs_readelf -m sim.elf > msize.txt` ON CS-3 and pull msize.txt, then
   add a --msize-file flag path (see Step 3 of pull_artifact.sh notes).
```

- [ ] **Step 2: Write the pull script**

```bash
# pull_artifact.sh  — usage: ./pull_artifact.sh CS3_REMOTE_DIR LOCAL_DIR
set -euo pipefail
REMOTE_DIR="$1"; LOCAL_DIR="$2"
mkdir -p "$LOCAL_DIR/executables"
# pull text-ish small files via base64-over-ssh (per EPCC transfer note)
for f in sim.map plan.json; do
  ssh CS-3-cmd "base64 -w0 $REMOTE_DIR/$f" | base64 -d > "$LOCAL_DIR/$f"
done
# per-PE ELFs (distinct binaries only — there are a handful)
for elf in $(ssh CS-3-cmd "ls $REMOTE_DIR/executables/*.elf"); do
  b=$(basename "$elf")
  ssh CS-3-cmd "base64 -w0 $elf" | base64 -d > "$LOCAL_DIR/executables/$b"
done
# msize: compute on CS-3 (sim.elf is large), pull the text
ssh CS-3-cmd "/home/lexu/Cerebras-SDK-2.10.0/cs_readelf -m $REMOTE_DIR/sim.elf" \
  > "$LOCAL_DIR/msize.txt"
echo "pulled artifact to $LOCAL_DIR (with msize.txt)"
```

- [ ] **Step 3: Add a `--msize-file` fallback to the extractor**

Modify `pe_mem/extract.py` `extract_artifact` signature to
`extract_artifact(artifact_dir, msize_file=None)`: if `msize_file` is given,
read `parse_msize(open(msize_file).read())` instead of calling `run_msize`
(so we don't need the giant `sim.elf` locally). Add the matching
`--msize-file` arg to `run_breakdown.py`. Add a unit test
`tests/test_extract_msize_file.py` that calls `extract_artifact` with a
temp dir containing `executables/` (symlinked from the sim fixture),
`sim.map` (copied), and a hand-written `msize.txt`, and asserts rows are
produced and reconcile.

```python
# tests/test_extract_msize_file.py
import os, shutil
from pe_mem.extract import extract_artifact

SIM = "/home/lexu/WaferEngine/models/qwen3_1p7b-decode/out_perfunc"

def test_extract_with_msize_file(tmp_path):
    d = tmp_path / "art"
    (d / "executables").mkdir(parents=True)
    for f in os.listdir(os.path.join(SIM, "executables")):
        if f.endswith(".elf"):
            shutil.copy(os.path.join(SIM, "executables", f), d / "executables" / f)
    shutil.copy(os.path.join(SIM, "sim.map"), d / "sim.map")
    # generate a real msize file from the fixture once:
    from pe_mem.cs_readelf import run_msize, parse_msize
    msize = run_msize(SIM)
    with open(d / "msize.txt", "w") as f:
        f.write("Memory used:\n")
        for (x, y), b in msize.items():
            f.write(f"({x}, {y}): {b} bytes ({b//2} words)\n")
    rows = extract_artifact(str(d), msize_file=str(d / "msize.txt"))
    assert rows
    bad = [r for r in rows if abs(r["code"]+r["weights"]+r["kv_cache"]
           +r["activations"]+r["system"] - r["total"]) > 2]
    assert not bad
```

Implementation change in `extract.py`:
```python
def extract_artifact(artifact_dir: str, msize_file: str = None) -> list:
    if msize_file:
        from pe_mem.cs_readelf import parse_msize
        coord_total = parse_msize(open(msize_file).read())
    else:
        coord_total = run_msize(artifact_dir)
    ...
```

- [ ] **Step 4: Run the new test**

Run: `python -m pytest tests/test_extract_msize_file.py -v`
Expected: PASS (1 passed). (This needs `cs_readelf`; if the SIF is unavailable in the dev env, mark `@pytest.mark.skipif` on missing wrapper.)

- [ ] **Step 5: Commit**

```bash
git add compile_on_cs3.md pull_artifact.sh pe_mem/extract.py tests/test_extract_msize_file.py
git commit -m "feat(pe_mem): CS-3 device-compile procedure + artifact pull + msize-file fallback"
```

---

### Task 10: Run on device artifacts (decode + prefill) and write results

**Files:**
- Modify: `README.md` (usage + interpretation)
- (Outputs go to the daily session log per the user's log-location routine, NOT committed in-repo.)

**Interfaces:** none new — this task *uses* the tool.

- [ ] **Step 1: Produce decode + prefill device artifacts**

Follow `compile_on_cs3.md` for both kernels (via the cs3-runner skill). Pull each into `device_artifacts/qwen3-decode/` and `device_artifacts/qwen3-prefill/` with `pull_artifact.sh`.

- [ ] **Step 2: Run the tool on each (device numbers)**

```bash
python run_breakdown.py --artifact device_artifacts/qwen3-decode \
  --kernel decode --config /home/lexu/WaferEngine/models/qwen3_1p7b-decode/model_config/test_device_2x2blk.json \
  --out results/decode --msize-file device_artifacts/qwen3-decode/msize.txt
python run_breakdown.py --artifact device_artifacts/qwen3-prefill \
  --kernel prefill --config /home/lexu/WaferEngine/models/qwen3_1p7b-prefill/model_config/test_device_2x2blk.json \
  --out results/prefill --msize-file device_artifacts/qwen3-prefill/msize.txt
```
Expected: per-role tables + PNGs for both; `reconciliation failures: 0`; record any `unclassified` symbols and extend `pe_mem/categorize.py` if non-trivial, then re-run.

- [ ] **Step 3: Write the results summary**

Append a results section to the daily session log (`/home/lexu/playground/research/logs/<date>-session-multi-request-brainstorm.md`): the per-role device tables, the heatmap/stacked PNGs, the headroom→max-seq-len numbers, and a short interpretation (code replicated everywhere, weights dominate, KV tiny, free residual → seq-len ceiling). Cross-reference the superseded `PE_SRAM_BREAKDOWN.md` / `PE_MEMORY_ANALYSIS.md`.

- [ ] **Step 4: Finalize README + commit**

```bash
git add README.md
git commit -m "docs(pe_mem): usage + device-run interpretation"
```

---

## Self-Review

**Spec coverage:**
- Extractor (`artifact_mem.py` role) → Tasks 2,3,4,6. ✔
- Symbol-driven categorizer with reconciliation → Task 5 (+ gate in Task 6 Step 5). ✔
- Renderer (heatmap + stacked + within-block + headroom) → Tasks 7,8. ✔
- Per-PE / central-vs-edge variation → coord-level rows (Task 6) + within_block plot (Task 7) + intra-block code-swing surfaced. ✔
- Device-compile-on-CS-3 + artifact pull (authoritative numbers) → Task 9. ✔
- Local sim fixtures for offline test → Tasks 2-8 integration steps. ✔
- Six exact categories + RoPE sub-bucket + 48 KB budget → constants (Task 1) + categorizer (Task 5). ✔
- Both kernels at device 2×2blk → Task 10. ✔
- Outputs (PNGs, CSV, summary table, results writeup) → Tasks 7,8,10. ✔

**Placeholder scan:** every code step has complete code; commands have expected output; no TBD/TODO. ✔

**Type consistency:** row dict keys are identical across Tasks 6/7/8 (`x,y,role,elf,total,code,weights,kv_cache,activations,system,free,rope,unclassified`); `breakdown()` returns exactly those category keys (Task 5); `render`/`role_summary` consume them (Task 7). `bytes_per_token_per_pe` name consistent Tasks 8. ✔

**Note on `cs_readelf` in dev env:** the offline integration steps (2-8) call `cs_readelf` only in Task 3/6/9 integration checks; pure-logic unit tests do not. If the SIF is unavailable where the plan is executed, those integration *checks* are skipped (not the unit tests), and Task 9's `msize.txt`-on-CS-3 path is the production route.
