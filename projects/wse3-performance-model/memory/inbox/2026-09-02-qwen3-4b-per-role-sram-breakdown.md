# Qwen3-4B per-role SRAM breakdown, decode capacity ceiling, and the local 4B compile recipe — 2026-09-02

**Project:** wse3-performance-model
**Author:** claude
**Status:** captured

## Situation

You need to know where the 48 KB per-PE SRAM goes in the Qwen3-4B role-split
placement (ATTN vs FFN, decode vs prefill) — e.g. when deciding whether a
placement change or code reduction can free room for resident KV cache — and
you are looking at compiled `executables/*.elf` plus `sim.map`.

## Finding (compiled-artifact measurement, SDK 2.10.0, local WSE3 target)

Source: WaferEngine `origin/main@b136ab64`, `models/qwen3_4b-decode` tree
`7120f908` (== frozen S3 worktree `93a6d0e`), `models/qwen3_4b-prefill` tree
`17ccc489`; configs `device_2x4_8k.json`+`device_prefill4k.json` and
`device.json` (8K, CHUNK 1024). Per PE, bytes (share of the 49,152 B bank):

| image | used | code (.text) | weights | KV cache (8K) | KV ingress | RoPE | activations | system | free |
| --- | --: | --: | --: | --: | --: | --: | --: | --: | --: |
| decode ATTN | 38,744 (78.8%) | 22,400 (45.6%) | 7,750 (15.8%) | 4,612 (9.4%) | 252 (0.5%) | 352 (0.7%) | 1,424 (2.9%) | 1,954 (4.0%) | 10,408 (21.2%) |
| decode FFN | 34,648 (70.5%) | 11,104 (22.6%) | 20,716 (42.1%) | 0 | 0 | 24 | 1,304 (2.7%) | 1,496 (3.0%) | 14,504 (29.5%) |
| decode HT tail | 44,934 (91.4%) | 14,140 (28.8%) | 23,780 (48.4%) | 0 | 0 | 0 | 5,500 (11.2%) | 1,514 (3.1%) | 4,218 (8.6%) |
| decode HT head | 27,350 (55.6%) | 2,380 (4.8%) | 23,760 (48.3%) | 0 | 0 | 0 | 24 | 1,186 (2.4%) | 21,802 (44.4%) |
| prefill ATTN (max variant) | 46,052 (93.7%) | 26,348 (53.6%) | 7,740 (15.7%) | 4,608 (9.4%) | – | 268 (0.5%) | 4,814 (9.8%) | 1,982 (4.0%) + 292 uncl. | 3,100 (6.3%) |
| prefill FFN (max variant) | 38,120 (77.6%) | 11,224 (22.8%) | 20,700 (42.1%) | 0 | – | 0 | 4,554 (9.3%) | 1,306 (2.7%) + 336 uncl. | 11,032 (22.4%) |
| prefill HT head | 40,492 (82.4%) | 2,000 (4.1%) | 23,760 (48.3%) | 0 | – | 0 | 1,538 (3.1%) + 12,076 (24.6%) rot_a/rot_b | 1,118 (2.3%) | 8,660 (17.6%) |
| prefill HT tail | 38,402 (78.1%) | 7,940 (16.2%) | 23,760 (48.3%) | 0 | – | 0 | 5,384 (11.0%) | 1,310 (2.7%) | 10,750 (21.9%) |

Appliance (CS-3, server 1.13.2) numbers for the decode compute PEs are
~600 B higher than the local build (`cs-readelf -m`: ATTN 39,328, FFN 34,944,
HT head 27,360, HT tail 45,584) because the appliance compiler emits
200–630 B more `.text`; every PE in a region is identical on silicon.

- On ATTN PEs code, not weights, is the #1 cost; `comm_mod.init` + route
  writers are 5.5–6.1 KB on every compute PE (boot-only), KV ingress 2.0 KB
  (round-start only) on decode ATTN.
- KV costs 0.5625 B/token/ATTN-PE (147,456 B/token wafer-wide; an 8K
  request = 1.125 GiB); every +256 tokens costs the ATTN PE 176 B (K+V 144
  + score 8 + score_f32 16 + kv_ingress_buf 8), measured 176.3 B/step.
- **Decode compile ceiling (local compile-only sweep, bsz 1, placement
  unchanged): MAX_SEQ_LEN = 23,040 (kv_len_per_pe 90) passes with 184 B free
  on the ATTN PE; 23,296 fails (`ld.lld: ran out of PE memory for task table`
  / `.data.hi`).** The zero-reserve estimate is one step too optimistic. FFN
  and HT tail are constant across the sweep.
- Prefill ATTN is the binding PE of the deployment (≈ +5 chunks of 1024
  before exhaustion; not swept).
- The FFN block carries 2.7× the weight bytes of the ATTN block on an
  identical 256×256 region and hosts no KV, so its 14.5 KB/PE free is
  unusable for KV under this placement.
- `models/qwen3_4b-decode` has no on-chip prefill compute: "prefill" = host
  streams K/V via `kv_ingress_buf` (248 B/PE). On-chip prefill is the
  separate `qwen3_4b-prefill` artifact.

## Gotchas (procedural; candidates for a skill)

- Both 4B device configs compile fully on gala2 with `cs_python launch_sim.py
  ... --compile-only` (`cmaddr=None`, WSE3 target): decode 27 s cslc, prefill
  186 s cslc, ~3 min single-threaded host weight bake each. Run from a copy
  under `/home/lexu` (the SIF binds `$PWD`, not `/tmp`).
- Decode ELFs are named by *source file* (`decode-18.elf`, `decode-19.elf`),
  not by region; map region→ELF via `sim.map` `$$csl_base_address$$` lines.
  `sim.map` addresses are 16-bit **word** addresses (ELF byte address / 2).
- Prefill emits 176 per-PE variants of each role image (differ in `.text` by
  ≤ 784 B); aggregate per family, don't expect one ELF per region.
- ELF sections at 0xF000–0xFDFF are PE config registers, 0xFE00+ is D-cache
  (`.csl_dcache` placed there by the model's `cslc-driver` wrapper); neither
  counts toward the 48 KB bank.
- Single-PE `cslc-driver` links inside the SIF (`singularity exec --bind $PWD
  --pwd $PWD <sif> cslc-driver --arch=wse3 src/decode.csl --single-pe ...`
  with the exact `--params` from the compile log) give per-image section sizes
  in seconds — use them for what-if sizing before a full-fabric compile.
  Module params (`comm_pe.csl`) must be forwarded through the top-level
  `@import_module` struct; `--params` only reaches the top-level file.

## Pointers

- `/home/lexu/wse3-performance-model/docs/analysis/2026-09-02-qwen3-4b-sram-usage-observation.md`
- `/home/lexu/wse3-performance-model/demo/analysis/` (script, results, provenance)
- artifacts: `/home/lexu/build/4b-sram/`
- ContextBase log: https://context.ed-aisys.com/doc/2026-09-02-result-qwen3-4b-decodeprefill-per-pe-sram-breakdown-by-role-K0mf3Dd2WF
- related topic: `projects/WaferEngine/memory/topics/pe-sram-memory-breakdown.md` (1.7B numbers, same method)
- companion capture: `2026-09-02-qwen3-4b-host-route-table-lever.md`
