# Editing the 2026-08-24 weekly deck (M3 multirow on-chip KV offload)

- `deck.json` is the slide text/specification; the built deck lives at
  `../2026-08-24.pptx`.
- `REPORT.md` is the full-detail report backing every slide (figure↔slide
  map, all device numbers, fit methods, caveats) — read it before editing
  any number.
- Figures under `figures/`:
  - `fig_samelaw.png` — regenerate with `python3 figures/fig_samelaw.py`
    (data inline, from the two device matrices).
  - `fig_v4_model_topology.png` — regenerate with
    `python3 figures/fig_v4_model_topology.py`; its topology panel is a
    derived crop of `v4_vs_v5.png`, whose editable source is the Excalidraw
    file below.
  - `fig_router_vs_ce.png` — regenerate with
    `python3 figures/fig_router_vs_ce.py`; values come from the device-fit
    coefficient table in `REPORT.md`.
  - `v4_vs_v5.png` — derived; the EDITABLE source is
    `WaferEngine-staging/docs/diagrams/m3-multirow-v4-vs-v5.excalidraw`
    (generator: scratchpad `gen_v4v5_diagram.py`; or edit the .excalidraw
    directly and re-export).
  - `tier_tradeoff.png` — regenerate with
    `python3 ../../assets/2026-08-24-m3-tier-tradeoff/fig_tier_tradeoff.py`.
  - `recap_e10d.png` — copy of the M2 E10D figure
    (`../../assets/2026-07-31-e10-ab-boundary/e10d_direct_flip.png`); do
    not edit, it is last week's measured artifact.
- Every number is a real CS-3 measurement except the L/~3000 projection
  (labeled projection) — see REPORT.md §5. v4 result-file meta says
  git-commit "2ffe1f6"; the true sources commit is b03bd6c.

Regenerate:

```bash
python3 /home/lexu/.claude/skills/wafer-slides/scripts/wafer_deck.py deck.json -o ../2026-08-24.pptx
python3 /home/lexu/.claude/skills/wafer-slides/scripts/validate_layout.py ../2026-08-24.pptx
python3 /home/lexu/.claude/skills/wafer-slides/scripts/render_preview.py ../2026-08-24.pptx preview 90
```
