# Editing the 2026-08-11 weekly deck

- `deck.json` is the slide text/specification.
- `make_figures.py` regenerates every figure as both editable SVG and presentation PNG under `figures/`.
- Edit an SVG directly in Figma, Illustrator, Inkscape, or a text editor; rerun the deck build after exporting the matching PNG.
- Performance charts use real CS-3 TSC. `eviction_model` is explicitly analytical and must retain that label until M3-E1 measures it.

Regenerate:

```bash
python3 make_figures.py
python3 /home/lexu/.codex/skills/wafer-slides/scripts/wafer_deck.py deck.json -o ../2026-08-11.pptx
python3 /home/lexu/.codex/skills/wafer-slides/scripts/validate_layout.py ../2026-08-11.pptx --strict
python3 /home/lexu/.codex/skills/wafer-slides/scripts/render_preview.py ../2026-08-11.pptx preview 90
```
