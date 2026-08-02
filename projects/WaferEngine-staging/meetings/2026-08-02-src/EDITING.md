# Editing the 2026-08-02 deck

The PowerPoint is generated from `deck.json`. Slide 3 uses the portable raster
image `figures/three_resume_lanes.png`.

For manual diagram edits, use `figures/three_resume_lanes.svg`. It preserves
text as text and boxes/arrows as vector elements. It can be edited in Figma,
Illustrator, or Inkscape. Recent desktop PowerPoint versions may also allow:

1. Insert the SVG onto a slide.
2. Right-click it and choose **Convert to Shape**.
3. Ungroup the converted graphic to edit individual labels, boxes, and arrows.

The canonical generated source is the "Three request paths" section of
`make_figures.py`. After source edits, regenerate figures and rebuild the deck:

```bash
python3 make_figures.py
python3 /home/lexu/claude-skills/wafer-slides/scripts/wafer_deck.py deck.json -o ../2026-08-02.pptx
```
