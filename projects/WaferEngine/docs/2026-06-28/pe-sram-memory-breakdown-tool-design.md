# Design: Systematic per-PE SRAM memory-breakdown tool for WaferEngine kernels

**Date:** 2026-06-28
**Status:** Design — approved in brainstorming, pending spec review
**Tool home:** `/home/lexu/WaferEngine/tools/pe_mem_breakdown/`
**Targets:** `models/qwen3_1p7b-decode` and `models/qwen3_1p7b-prefill`, device `test_device_2x2blk.json` (P_BLOCK_SIZE=256)

---

## 1. Goal & motivation

Build a **systematic, repeatable** tool that, given a compiled CSL artifact for a WaferEngine
kernel, computes **each PE's 48 KB SRAM usage** split into:

- **code** (`.text`)
- **weights / parameters** (banked + non-banked weight symbols, incl. embedding & lm_head)
- **KV cache** (the K/V cache symbols)
- **activations / scratch** (per-token working tiles)
- **system / runtime** (`.task_table`, `.fabric_routes`, `.bss` residue, DSR init, stack reserve)
- **free** (48 KB − used)

and renders:

1. a **fabric heatmap** (per-PE-coordinate, colored by used bytes or free %), exposing
   **central-vs-edge variation within a PE block**, and
2. a **per-PE-role stacked breakdown** against the 48 KB ceiling, plus a printed table and a
   **headroom → max-seq-len** annotation.

This replaces the hand-built one-off analyses
`/home/lexu/WaferServe/kernels/Decode-GQA/docs/PE_SRAM_BREAKDOWN.md` and
`PE_MEMORY_ANALYSIS.md` (same methodology, but those were manual, single-config, and Llama-8B)
with an automated tool that runs on any artifact and emits plots.

### Why this matters (the Cerebras memory story)
Unlike a GPU's shared HBM, the WSE has **disaggregated SRAM**: every PE has its own 48 KB, and
**both the program code and the model parameters are replicated/sharded across hundreds of
thousands of PEs**. The code (`.text`) is replicated on every PE; weights are sharded but still
consume per-PE SRAM. After code + weights + system overhead, **only a small residual is free for
KV cache**, which is what caps the supported sequence length. The tool makes this budget visible
and quantitative.

### Key architectural facts (verified in brainstorming)
- **All PE memory is statically allocated at compile time** — no malloc/HBM. The KV cache is a
  fixed-size array reserved at compile time; "dynamic" only means *how much of that reserved
  array is filled* at a given sequence position. So the full breakdown is determined by the
  **compiled artifact**; running on silicon does not change the numbers (only confirms it fits).
- **Where you compile matters.** The real WSE-3 compiles with fabric dims `762,1172`; a
  `cmaddr=None` simulator compile produces a tight-fabric artifact with different placement/
  routing. Authoritative numbers therefore require compiling the **device config on CS-3** with
  the live `--cmaddr`.
- **Data sections are PE-independent; code/routing are not.** From the prior Llama-8B analysis:
  `.bss` (weights + KV) is byte-identical on every PE, but `.text` swings ~200 B between corner
  (17,890 B) and interior (18,094 B) PEs due to different inlining/fabric-routing outcomes. This
  is the central-vs-edge variation the tool must surface, and it lives in **code + routing**, not
  data.

---

## 2. Inputs, fidelity, and the device-compile path

**Fidelity decision (user):** numbers must come from an artifact **compiled on the actual CS-3
machine** for the real fabric — not a local simulator compile, and not pure formula estimates.

**Device-compile path (authoritative run):**
1. Launch a CS-3 wsjob via the `cs3-runner` skill (honor the OTP/ControlMaster rules in memory).
2. Run each model's existing device entry (`launch_device.py` / `run_device.sh`) with the live
   `--cmaddr=%CMADDR%` so `SdkLayout.compile()` sizes the artifact for `762,1172`.
   **Compile-only is sufficient for the memory numbers**; a load/run is optional confirmation
   that it fits. Compile + artifact retrieval is the required minimum.
3. Retrieve the artifact's `executables/*.elf`, `sim.map`, `plan.json`, and the per-PE
   `*.json` back to local via base64-over-ssh (per the EPCC file-transfer note — no rsync/scp).
4. Feed the local copy of the artifact dir to the extractor.

**Local development fixture (no cluster needed):** the existing
`models/qwen3_1p7b-decode/out_perfunc/` and `models/qwen3_1p7b-prefill/out_s47/` are *simulator*
compiles (reduced params) but **format-identical** to the device artifact. The extractor and
categorizer are built and unit-tested against these offline before pointing at the device
artifact. Only the *numbers* differ between sim and device; the *parsing* is identical.

---

## 3. Architecture — three decoupled units + a driver

All under `/home/lexu/WaferEngine/tools/pe_mem_breakdown/`.

### 3.1 `artifact_mem.py` — extractor (artifact dir → tidy rows)
Pure data extraction; no plotting, no opinions about categories.
- Run `cs_readelf -m <artifact>` (binary at `/home/lexu/Cerebras-SDK-2.10.0/cs_readelf`) to get
  the **authoritative per-coordinate total** `(x, y) → bytes`. This captures *all* per-PE
  variation including code/routing.
- Build a **coordinate → ELF/role** map. WaferEngine's SdkLayout dedups identical binaries, so
  `executables/` holds a handful of distinct ELFs per region (e.g. `decode-15.elf … decode-22.elf`
  = 8 distinct decode roles). Map each fabric coordinate to its ELF using `plan.json` + the per-PE
  `*.json` + the placement coordinates in `launch.py` (`DEMUX_FAB_X`, `HT_HEAD_X`, `PLACE_X`, row
  bands). Fallback: parse `sim.map` symbol coordinates.
- For each distinct ELF: section sizes via `readelf -SW` (`.text`, `.data`, `.data.lo`,
  `.data.hi`, `.bss`, `.task_table`, `.fabric_routes`) and per-symbol sizes via `readelf -sW`
  (FUNC rows → code attribution; OBJECT rows → data symbols). Resolve section index → name
  dynamically (do not hardcode "section 15/16" — that was config-specific in the prior doc).
- **Output:** a tidy table written to CSV — one row per `(pe_x, pe_y, role, elf, category, bytes)`
  — plus a per-coordinate `total_bytes` column from `cs_readelf`. The CSV is the stable interface
  between extraction and plotting.

### 3.2 `categorize.py` — classifier (symbol/section name → category)
**Attribution is symbol-driven, not section-driven.** Critically, weights, KV cache, and
activations all live *inside `.bss`* (confirmed by the prior Llama-8B analysis: `.bss` = banked
weights + KV + activation tiles in one section) — so they cannot be separated by section name.
The classifier sums **per-symbol bytes** (`readelf -sW` OBJECT rows / `sim.map`) and buckets each
symbol by name. Sections are used only for `.text` (code) and for the **residual**:
`system = (all section bytes) − (symbols already attributed) − .text`. This keeps the accounting
exhaustive and reconcilable. A single auditable name→category mapping, with per-kernel symbol
lists derived from the source (already catalogued in brainstorming):
- **weights:** `*_weight_tile`, `W_qkv_bank`, `W_o_bank`, `W_upgate_bank`, `W_down_bank`,
  `*_norm*_(tile|bank)`, `q_norm*`, `k_norm*`, `lm_head_tile`, `W_E_tile`, `W_final_norm_tile`,
  `we_buf_*`
- **rope** (reported as a labeled sub-bucket of weights): `freqs_*`, `cos_*`, `sin_*`, `delta_*`
- **kv_cache:** `XKCache_tile`, `XVCache_tile`, `K_cache_bank`, `V_cache_bank`, `V_stash`
- **activations:** `X_tile`, `X_norm`, `QKV_*`, `score*`, `ffn_*`, `z_upgate`, `z3`, `h1`, `h2`,
  `Z*`, `attn_*`, `scratch_*`, `*_f32`, `sq_f32`, `local_*`, `output_tile`
- **code:** `.text`
- **system:** `.task_table` + `.fabric_routes` + `.bss` residue + `.data.lo` (DSR init) + stack
  reserve
- **free:** 48 KB − used
Anything unmatched is emitted as **`unclassified`** (never silently dropped) and reconciled:
`sum(categories) == cs_readelf total` per PE must hold (assertion / warning if off by > a small
tolerance).

### 3.3 `plot_mem.py` — renderer (tidy CSV → PNG + summary)
- **Fabric heatmap:** scatter/imshow over `(pe_x, pe_y)`, colored by total used bytes (and a
  second panel by free %). Region boundaries annotated (demux / HT_head / decode rows / HT_tail /
  mux). This is where central-vs-edge code/routing variation is visible.
- **Stacked breakdown:** one stacked bar per distinct PE-role, segments = the six categories,
  drawn against the 48 KB ceiling line. Shows the code/weights/KV/free split per role.
- **Within-block variation panel:** for a chosen region (decode block), a small plot of the
  per-role spread (e.g. `.text` min/median/max across the distinct ELFs) to make the
  corner-vs-interior swing explicit.
- **Headroom annotation:** free bytes per role → estimated additional KV tokens, with the
  per-token KV cost computed from the config (stating the sharding assumption: KV is sharded by
  sequence position, so the marginal token lands on one PE-turn per layer, not uniformly — the
  annotation is a first-order ceiling, labeled as such).
- **Output:** one PNG per kernel + a printed per-role table (bytes and % of 48 KB) + the
  reconciliation / `unclassified` report.

### 3.4 `run_breakdown.py` — driver / CLI
`run_breakdown.py --artifact <dir> --kernel {decode,prefill} --out <dir>` wires extractor →
categorizer → renderer. A separate `--compile-on-cs3` mode (or a thin shell wrapper) drives the
cs3-runner device-compile + artifact pull, then invokes the local pipeline. Plotting is fully
decoupled from compilation: re-plotting needs only the CSV.

---

## 4. Data flow

```
CS-3 wsjob compile (device cmaddr)  ─┐
                                     ├─►  artifact dir (executables/*.elf, sim.map, plan.json)
local sim artifact (dev fixture)  ──┘
        │
        ▼   artifact_mem.py  (cs_readelf -m + readelf -S/-s + plan.json)
   tidy CSV  (pe_x, pe_y, role, elf, category, bytes, total_bytes)
        │
        ▼   categorize.py     (symbol/section → 6 categories, reconcile vs total)
   categorized CSV
        │
        ▼   plot_mem.py
   heatmap.png + stacked.png + within_block.png + summary table + report
```

---

## 5. Testing strategy

- **Unit tests** against the local sim artifacts (`out_perfunc/`, `out_s47/`): assert the
  extractor parses every distinct ELF, that `cs_readelf -m` totals are recovered, and that
  `sum(categories) == total` per PE within tolerance.
- **Categorizer tests:** a fixed set of known symbol names map to the expected category; no symbol
  lands in `unclassified` for the two target kernels (or, if it does, the test prints them so the
  map can be extended).
- **Reconciliation gate:** for every PE, `code + weights + kv + activations + system + free`
  equals the 48 KB budget and the used portion equals `cs_readelf -m`. A failing reconciliation
  is a hard error, not a silent rounding.
- **Cross-check:** the decode device numbers should be in the same ballpark as the prior
  hand-analysis structure (weights dominate, KV tiny, `.text` ~18 KB, free a few hundred bytes to
  a few KB) — sanity, not exact (different model/config).

---

## 6. Outputs (deliverables)

- `tools/pe_mem_breakdown/` with the four scripts + a short README (how to run locally and on
  CS-3).
- For each kernel: `<kernel>_heatmap.png`, `<kernel>_stacked.png`, `<kernel>_within_block.png`,
  `<kernel>_breakdown.csv`, and a printed/saved summary table.
- A short results writeup (numbers + interpretation) appended to the daily session log per the
  user's log-location routine (not in the repo).

---

## 7. Scope boundaries (YAGNI)

- **In:** decode + prefill at device `test_device_2x2blk.json`; the six-category per-PE breakdown;
  the three plots; the CS-3 device compile + artifact pull; local-fixture tests.
- **Out (for now):** config sweeps (multiple seq_len / P_BLOCK_SIZE); `.text` optimization levers
  (the prior docs cover that — this tool *measures*, it does not optimize); WSE-2; non-qwen
  kernels. The tool is built so these are easy follow-ons (extractor is config-agnostic).

---

## 8. Risks & mitigations

- **CS-3 operational friction** (wsjob queue 5+ min, 502 transients, OTP, no worker egress): use
  the cs3-runner skill and its established protocols; compile-only keeps the job short; the local
  fixtures de-risk all parser development so the cluster is only needed for final numbers.
- **Coordinate→role mapping ambiguity:** if `plan.json` is insufficient, fall back to `sim.map`
  symbol coordinates and the explicit placement constants in `launch.py`. Validate by checking
  region sizes sum to the placed fabric extent.
- **`cs_readelf` availability/format drift:** pin the SDK path; if `-m` output format differs,
  cross-check against `size`/`readelf -S` section sums.
- **Sim vs device divergence:** never present sim numbers as device numbers; the CSV records which
  artifact (and fabric dims) it came from.
```
