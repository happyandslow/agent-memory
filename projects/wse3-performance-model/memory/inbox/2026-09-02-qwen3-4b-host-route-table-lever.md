# Qwen3-4B: host-computed route table replaces `comm_mod.init` — CS-3 verified, +5 KB/PE — 2026-09-02

**Project:** wse3-performance-model
**Author:** claude
**Status:** captured

## Situation

You want more resident KV context on the Qwen3-4B decode ATTN PEs without
changing the placement, and the largest per-PE cost is the 22.4 KB program
binary — of which `comm_mod.init` (5,632 B) derives every route word and
runtime scalar from the wafer coordinates once at boot and never runs again.
Paging that code (WaferLLM `pageability-demo` style shared slot) has a
measured negative economics (+3,182 B receiver); linker overlay of a data
section onto the retired code is rejected by lld (`section ... overlaps`).

## Decision and result

Replace the on-device derivation by a **host-computed per-PE table**:
`host/route_table.py` transliterates `route_calc.get_params` + the static
route case analysis of `init()`; per PE it emits 34 u16 (12 runtime scalars,
the rx|tx low byte of the 13 axis route words, ≤ 7 static route low bytes
with 0xFFFF = untouched, 2 ingress queue color ids) uploaded as `pe_cfg` via
`set_symbol_all` next to the weights. On device, `init_from_table()` (812 B)
ORs each low byte under the live color register's preserved high byte
(rx bits 0x00/0x20/0x40/0x60/0x80 = W/E/S/N/RAMP, tx 0x01/02/04/08/10) and
applies queue bindings. `use_route_table` / `route_check` params keep the
legacy path selectable; `route_check=1` runs both and counts disagreements.

Measured (working copy `/home/lexu/build/4b-sram/routetable/`, not merged):

| | baseline | route table |
| --- | --- | --- |
| ATTN PE SRAM, appliance `cs-readelf -m` | 39,328 B (80.0%) | **34,080 B (69.3%)** |
| FFN PE SRAM | 34,944 B (71.1%) | **30,272 B (61.6%)** |
| decode MAX_SEQ_LEN compile ceiling (local sweep) | 23,040 | **30,464** (1.32×) |
| CS-3 outputs, 4096 prefill + 4096 decode, bsz 1 | `wsjob-rcbpvpt6cay6aomhuujnx9` | `wsjob-amzrrqt78wnfxoxy9blpyq`: **byte-exact identical** (all top-20 vals/idx + sampled ids) |
| device TSC per token | 785,768.7 cyc | 785,826.2 cyc (+0.007%) |

Simulator gates first: `route_check` 0/1,024 PE mismatches; table-only image
bit-identical outputs and identical simulated TSC vs baseline over 3 rounds
with re-arm. Report: `demo/analysis/results/cs3_baseline_vs_routetable.md`;
diff: `results/route_table_src.diff`.

## Rejected alternatives (measured)

- Runtime-length merge of the five `all_reduce_*` variants: **+532 B** — every
  runtime `@set_dsd_length` on a fabric DSD is materialised in code, while
  comptime extents are constants in `.data.lo`.
- Sharing one comptime length (`shared_reduce_len`: ATTN O-proj 10→25 and
  Score@V 20→25 elements ride the QKV_FUSION_LEN reduce): **−1,136 B on the
  ATTN PE but +0.39 % per token on CS-3** (785,826 → 788,911 cyc,
  `wsjob-78ms8yjwm6rvfwyr2gq58m`, byte-exact outputs). A trade, kept off by
  default; padding a chained all-reduce costs ≈ 100 cyc/layer here.
- Boot-code overlay (`linksection(".boot_code")` pinned at 0xA800, KV
  addressed by `@bitcast` pointer into the retired range): links (`.text`
  22,400 → 16,624) but needs per-layer slab tables and loses the sim
  `read_symbol` seed check for the retired-range slabs; superseded by the
  table.

## Gotchas (CS-3 operations)

- `SdkLauncher.download_artifact` takes exact remote names, no globs — tar
  the per-role ELFs worker-side (`executables.tgz`) and download that.
- Worker-side `cs-readelf -m sim.elf` on the 665K-PE image takes seconds and
  yields a 22 MB `msize.txt`; it is identical between a real run and a
  compile-only job of the same source, so SRAM numbers can come from
  compile-only jobs.
- Appliance ELFs are not byte-identical to local SDK 2.10.0 ones (+200–630 B
  `.text` per image); compare allocated section sizes, not file hashes.
- A device run of this config is ~4 min wall (compile 24 s, decode 4.56 s for
  4096 tokens); 3600 s guard was ample.

## Implications / next actions

- [ ] Run the 30,464-capacity image on CS-3 (only compile-swept so far).
- [ ] Decide whether to move the route-table patch into an isolated WaferEngine
  worktree for review (Le's call; nothing committed anywhere).
- [ ] The same lever applies to prefill ATTN (26 KB `.text`, 3.1 KB free) —
  separate artifact, not attempted.

## Pointers

- `/home/lexu/wse3-performance-model/docs/design/2026-09-02-attn-column-split-compute-storage-hypothesis.md` (Addendum A1–A4)
- `/home/lexu/wse3-performance-model/demo/analysis/results/` (`route_table.py`, `route_table_src.diff`, `cs3_baseline_vs_routetable.md`, `cs3/`)
- ContextBase: https://context.ed-aisys.com/doc/2026-09-02-result-qwen3-4b-decodeprefill-per-pe-sram-breakdown-by-role-K0mf3Dd2WF
- companion capture: `2026-09-02-qwen3-4b-per-role-sram-breakdown.md`
