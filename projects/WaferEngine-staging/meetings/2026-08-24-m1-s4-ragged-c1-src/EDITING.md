# M1-S4 C1-M Weekly Insert

This directory is the independently buildable source for slides 9–12 of the 2026-08-24 weekly deck. The standalone insert is stored at `../2026-08-24-m1-s4-ragged-c1.pptx`.

## Slide map

1. Motivation: common-start replay is correct but recomputes the longer prefix hit.
2. Mechanism: green stages are predicated for an inactive lane; yellow stages still execute; grey work remains fixed at full batch extent.
3. Device result: 37.49% less timed lane-step work produced no measurable critical-path speedup on the matched C1-M construction.
4. Next decision: either profile the fixed floor or scope C2 / continuous batching with independent lane progress.

## Source and regeneration

- `deck.json` is the editable slide specification.
- `figures/decode_step_c1_scope.excalidraw` is the editable mechanism diagram.
- `scripts/make_c1_result_plot.py` regenerates the result plot from the recorded four-point device summary.
- `figures/last_week_ragged_execution.*` is copied from slide 7 of the 2026-08-11 collaborator deck for continuity.

From this directory:

```bash
python3 scripts/make_c1_result_plot.py
inkscape figures/decode_step_c1_scope.svg --export-filename=figures/decode_step_c1_scope.png
python3 /home/lexu/.claude/skills/wafer-slides/scripts/wafer_deck.py deck.json -o ../2026-08-24-m1-s4-ragged-c1.pptx
python3 /home/lexu/.claude/skills/wafer-slides/scripts/validate_layout.py ../2026-08-24-m1-s4-ragged-c1.pptx
python3 /home/lexu/.claude/skills/wafer-slides/scripts/render_preview.py ../2026-08-24-m1-s4-ragged-c1.pptx preview 90
```

The final build contains four slides and passes strict layout validation with zero warnings. All four rendered previews were visually inspected on 2026-08-24.

## Evidence boundary

The device point is full-model Qwen3-1.7B, `bsz=2`, `S/N/F/G=256/1024/769/255`, five repetitions for each of `K=0/256/512/768`, using raw TSC cycles. Speedup is relative only to the construction-matched manual `K=0` baseline. The automatic Experiment-A `K=0` point is not ratio-compatible with this construction.

The result supports a throughput NO-GO for the current fixed-communication C1-M mechanism. It does not establish end-to-end serving throughput, fairness, energy savings, or the value of C2 / continuous batching.
