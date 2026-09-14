# KV farm: first end-to-end runs (simfab + CS-3), the route-programming early-return hang, and the simfab hang-diagnosis recipe — 2026-09-13

**Project:** wse3-performance-model
**Author:** claude (session 4b-layout-kv-stream)
**Status:** captured

## Situation

You are integrating a multi-PE protocol (here the compute-at-storage KV farm)
into the Qwen3-4B decode block, the run hangs in step 0 on both simfab and
CS-3, simfab reports `Stopping due to fatal error` + SIGSEGV with no PE
message, and the CTF trace ends before the hang.

## Findings

- **Root cause of the hang:** `kv_farm.csl:program_routes` returned early for
  stub PEs (`col < head`) after their own routes, skipping the level-3
  class-column *pass-through* routes. Head 0's column chain died at the first
  head-1 row, the head-0 root never sent H, band 0's keepers waited forever.
  Rule: a PE must program routes for every colour that transits it, not only
  the ones it sends/receives — audit every early `return` in per-role route
  code, and test every head/class, not just the first that happens to work.
- **`Stopping due to fatal error` + SIGSEGV is the simulator's idle stop**
  (≈ 20K cycles of no data movement) with a host receive pending; the message
  printer segfaults. It is a plain hang. Real simulator checks print a
  PE-tagged line (e.g. `Attempt to remap input queue … not empty`).
- **The CTF trace loses ≈ 600K events per stream on that abort**, so its end
  is not the hang point. The readable state is a **core dump** taken by the
  host before the idle stop: `launch.py` `SIM_STALL_S` (nonblocking receive +
  `is_task_done` poll + `runtime.dump_core`); `read_symbol`/`stop()` are not
  usable there. Core format and readers: `/home/lexu/build/4b-farm/repro/
  core_dbg.py`, `ctf_tail.py` (documented in the personal memory
  `simfab-stall-diagnosis-recipe`). Per-PE phase words (`export var
  farm_dbg[4]` written at each protocol step) made the state legible in one
  read.
- **Bisect knobs can create hangs of their own** (stage 1 never restored
  IQ2; stages 7/8/9 ran the late merge because the guard was `>= 2`). Two
  device jobs were spent on those. Validate a knob's own liveness in the sim
  before spending a device job on it.
- **Colour/queue facts:** id 7 is a layout port colour (`tok_bcast` connect)
  — never on block links; ATTN can borrow IQ2 (intra-row bcast receive) and
  OQ0, not IQ0 (next step's x lands asynchronously; remapping a non-empty
  input queue is a simulator fatal). 16-bit `@mov16` fabric moves carry two
  bf16 per wavelet.
- **Numbers (CS-3, prefill 512 / decode 64, 47 timed tokens):** shipped
  baseline 672,193 cyc = 790.8 µs/token; farm image + routes/rebinds only
  810.4 µs (+2.5 %); full farm protocol (zeros, 6 positions/PE)
  3,760,395 cyc = 4,424 µs (**5.6×**). Simfab `sim_2x2` tiny: 136,016 vs
  59,357 cyc. The serial 3-level chain (≈ 36 hops of 520 f32, O staged
  through memory) is the cost; the topology is correct.

- **Router "fabric adder" is real but unreachable:** the SDK 2.10 simulator
  models per-colour `fab_adder_cfg/en/bias/sexp` registers (`libfscore.so`
  strings), but CSL 2.10 has no builtin, `tile_config` module, doc or example
  for it (csl-knowledge and the container's kernel sources: zero hits). Do not
  design the merge around in-fabric reduction; CE streaming adds are the tool.

## Implications / next actions

- [ ] Stream the merge hop (`@fmacs(fabout, mem, fabin, a)`), then tree merges
  (log depth) in groups and on the class column; re-measure on CS-3 before
  any capacity claim. Record in `analyses/2026-09-13-kv-farm-v3-sim-integration/`.
- [ ] Only then the context sweep (penalty curve) and S4.
- [ ] Promote the stall-diagnosis recipe into the `cs3-run`/simfab skills.

## Pointers

- `analyses/2026-09-13-kv-farm-v3-sim-integration/README.md`,
  `docs/design/2026-09-02-kv-farm-s4-layout.md` §10
- CS-3: `~/rsync/4b-farm-s1-rsync/`, `~/rsync/4b-farm-s1-logs/FARM_R.log`
  (`wsjob-wcimxkulfw6m6ryx64ca4r`), `BASE_R.log` (`wsjob-rouhn8djwqvn6zwsupoquy`)
- related: `2026-09-13-kv-farm-late-merge-small-scope-sync.md`,
  `2026-09-13-large-kernels-run-on-cs3-not-simfab.md`
