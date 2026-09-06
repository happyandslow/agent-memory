# Figure/deck pipeline: transAxes autoscale wipes text; two pythons — 2026-08-24

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured

## Situation this applies to

Generating weekly-deck figures (matplotlib panels with hand-placed text) and
building the deck under `meetings/<date>-src/`; any matplotlib figure that
mixes `transform=ax.transAxes` artists with default-transform text.

## The two gotchas

1. **`ax.plot(..., transform=ax.transAxes)` still feeds autoscale.** Plotting
   a decorative line with transAxes on an otherwise-empty axes collapsed the
   DATA limits to a sliver around the line's y-value, so every `ax.text(...)`
   placed in default (data) coordinates fell outside the view — the figure
   rendered with patches visible and ALL text silently missing (0 dark
   pixels; no warning). Cost three debug rounds because the blank output was
   first blamed on the conda env. **Fix:** on text-panel axes, immediately
   `ax.set_xlim(0,1); ax.set_ylim(0,1); ax.set_autoscale_on(False)` after
   creating the axes (or give every artist an explicit transform).
   Symptom signature: rectangles/lines render, text vanishes, savefig quiet.

2. **The deck pipeline spans two interpreters.** `wafer_deck.py` /
   `validate_layout.py` need `pptx` — present in conda base
   (`source ~/miniconda3/bin/activate`), absent in `/usr/bin/python3`.
   Matplotlib figure scripts run in either. Symptom when crossed:
   `ModuleNotFoundError: No module named 'pptx'` from the system python.

**Why:** both failures are silent-or-late and each burned a build/render
round on 2026-08-24; the autoscale one produces a "valid" but empty figure
that only visual inspection catches — exactly the artifact class the
wafer-slides step-4 eyeball rule exists for.

**How to apply:** lock limits + autoscale off on any hand-placed-text axes;
run figure scripts with whichever python, run the deck build/validate/render
steps under conda base.
