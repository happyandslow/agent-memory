# Figure convention Le wants for on-chip data-flow designs: one fixed base layout, one frame per timestep — 2026-09-13

**Project:** wse3-performance-model
**Author:** claude (session 4b-layout-kv-stream)
**Status:** captured
**Kind:** procedural / feedback (promotion candidate)

## Situation

You are explaining a multi-step on-chip protocol (who computes what, what
crosses which links, in what order) to Le with figures, and you are tempted
to draw a swimlane / sequence diagram or a per-step schematic with its own
geometry.

## What Le asked for (verbatim intent, 2026-09-13)

- "Timestep" means **one figure per step**, and the content of every frame is
  **the same base layout** (the floorplan already drawn) with that step's
  message flow / computation overlaid. A swimlane with lanes is not what was
  meant.
- Earlier explanatory figures should reuse **the same base layout** to
  reduce reading cost — schematics with their own geometry cost him
  re-orientation each time.
- He then asked for all frames **combined into one image** as well.

## Recipe that satisfied it

- One `base_layout()` function draws the fixed floorplan (regions, head
  bands, root row, example row, hairlines) at a scale/origin read from a
  small globals dict; overlays are functions of `(canvas, geometry, font)`.
- Two consumers of the same spec list: single-frame files at 1.5 px/PE with a
  wide caption box, and a 3 × 3 contact sheet at 1.0 px/PE (`t_sheet()`).
  Same drawing code, so the frames and the sheet cannot drift.
- Colour each overlay by **synchronisation scope** (local / 2-party stream /
  small group / existing wide collective) — that is the property Le reads
  the frames for.
- Keep captions with cost + sync scope per frame; keep CJK out of rendered
  text (the export font has no CJK glyphs; the PNG shows blanks).
- Excalidraw source stays the editable truth (`exlib.py` writes
  `.excalidraw` + SVG + PNG in one call).

## Promotion signal

Procedural and likely to recur for every kernel/protocol design review in
this project (and WaferEngine-staging). Proposed as a small addition to the
`excalidraw-diagrams` skill: "for protocol/timestep figures, fix one base
layout and overlay per step; provide a combined sheet". Not installed.

## Pointers

- `docs/diagrams/gen_2026-09-02-kv-farm-figures.py` (`base_layout`,
  `T_SPECS`, `t_series`, `t_sheet`), `docs/diagrams/exlib.py`
- outputs: `docs/diagrams/2026-09-02-kv-farm-step-t0..t8.png`,
  `2026-09-02-kv-farm-steps-sheet.png`
