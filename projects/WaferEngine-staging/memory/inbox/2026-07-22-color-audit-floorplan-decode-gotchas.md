# csl-color-audit floorplan/matrix is misleading for a decode config — 2026-07-22

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured   <!-- captured | drained -->

## What happened / finding

**Situation:** you run `csl-color-audit models/qwen3_1p7b-decode --worktree --config <a decode config> --floorplan` (or open the color matrix), and you are trying to see where the KV-ingress `kv_ingress_adaptor` / `kv_ingress_injector` PEs sit, or to reason about the decode layout. Three traps, all of which cost real misdiagnosis time this session:

1. **The floorplan predicts the FUSED e2e region template, so a pure-decode floorplan shows spurious `pf_block` / `pf_ht_head` / `pf_ht_tail` / `pf_demux` / `pf_logits_mux` / `relay` regions** — the *prefill half*, which a standalone decode kernel never builds. Symptom: "why is there a `pf_block` on my decode floorplan, and is this even the decode kernel?" It is; those regions are an artifact of `report_floorplan.predict_regions` modeling the fused floorplan (decode is the leading prefix + a spurious prefill tail). Authoritative placement is always `launch.py`'s `create_code_region`, not this predicted view.

2. **1-PE-wide regions render as tiny numbered badges + side-table rows, NOT labeled boxes** — so `kv_inj_*` (1×P_BLOCK_SIZE), `kv_adp_*` (1×1), `x_demux` "look missing" on the rendered image. They are present: check the "Code regions" side table and the badge numbers on the east edge. I first grep'd only the inline `>label<` text of *wide* blocks and wrongly concluded the injector/adaptor were dropped. `predict_regions` does emit them (gated on `KV_TRANSFER!=0 and not fused`; verified by calling it directly). Fixed the renderer this session to give narrow-but-tall strips a rotated label (`report_floorplan.py render_floorplan_svg`, `elif h_px > 44` branch) — but the badge-only behavior for 1×1 regions remains.

3. **The color/queue MATRIX view cannot map the switch/router-driven helper PEs at all** (injector/adaptor/demux/mux/kv_*). Their tasks make no collective/`reconfig` calls, so the stage extractor produces **zero columns** → an empty matrix even with `--entry <a task in the file>`. The matrix is an entry-scoped *decode layer-body* map only. So for KV-ingress drain/rebind reasoning, this tool gives you nothing; read the CSL + `launch.py` directly.

**One-line gotcha:** for the KV-ingress staircase and decode-vs-fused region attribution, csl-color-audit is unreliable — floorplan superimposes fused prefill regions and renders thin PEs as badges; the matrix omits switch/router PEs entirely.

## Implications / next actions

- [ ] (procedural / possible skill-doc promotion) The three traps above are tool-reading knowledge, not a WaferEngine-staging fact — candidate for a note in the `csl-color-audit` SKILL.md ("what this tool does NOT reliably show"). Propose to Le; do not edit claude-skills from here.
- [ ] Optional real fix (deferred): gate the `pf_*` / `relay` fused regions OFF for flat (non-fused) decode configs in `predict_regions` — but that touches the pinned `test_predicted_floorplan_matches_the_probe_exactly` (e2e) test, handle carefully.

## Pointers

- Skill: `~/claude-skills/csl-color-audit/analyzer/report_floorplan.py` (`predict_regions` gate ~L93 `fused = "decode" in cfg and "prefill" in cfg`; `render_floorplan_svg` label branch this session's edit).
- Related project note: `memory/topics/s6a-decode-kv-retain.md` (the KV-ingress adaptor/injector this floorplan was being used to inspect).
- Rendered artifact: `assets/color-audit/qwen3_1p7b-decode@<worktree>+test_sim_2x2block_kv_retain_chain.svg`.
