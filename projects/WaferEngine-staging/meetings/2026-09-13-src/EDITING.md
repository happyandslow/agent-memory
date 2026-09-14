# Editing the 2026-09-13 weekly deck

`deck.json` is the slide spec; the built deck is `../2026-09-13.pptx`.
`collected.md` is the input record: every number on a slide traces to an entry there.

Regenerate:

```bash
S=~/.claude/skills/wafer-slides/scripts
python3 $S/wafer_deck.py deck.json -o ../2026-09-13.pptx
python3 $S/validate_layout.py ../2026-09-13.pptx     # must print OK
python3 $S/render_preview.py ../2026-09-13.pptx preview 90
```

## Shape (draft v1, 54 slides)

1–38 talk: title, one-statement summary, then seven sections — workload (3–7),
GPU baseline (8–10), capacity (11–16), prefix × decode spectrum (17–23),
layout C (24–31), kernel fixed term (32–33), industry context and positioning
(34–37) — and the decision list (38).
39–42 Corrections, 43–54 Appendix. Every table and every figure has its own slide.

## Pending Le

- Clock: every CS-3 tok/s is at 750 MHz as the source sessions reported.
  Le's 09-07 rule is 0.85 GHz (× 1.133). Affects slides 9, 14, 18–20.
- Rounds 166–170 of the wide-layer report (R167 "a fixed system prompt is
  weights", R168 "a 4B never serves the Claude Code model") are not on any slide.
- Figures: `figures/attn_vs_ffn_three_axes.png` is the source PNG with the
  clipped footnote cropped; the FLOP-panel subtitle still collides with the
  1200 tick. `figures/layoutC_placement_map.png` is the left panel of the
  colour-regions figure; it is document-density and does not read on a projector.
- The compare slide (36) marks neither option — the residency framing is
  4b-wide-layer's proposal, not a decision.
