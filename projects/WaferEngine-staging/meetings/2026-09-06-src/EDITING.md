# Editing the 2026-09-06 weekly deck

`deck.json` is the slide spec; the built deck is `../2026-09-06.pptx`.

Regenerate:

```bash
S=~/.claude/skills/wafer-slides/scripts
python3 $S/wafer_deck.py deck.json -o ../2026-09-06.pptx
python3 $S/validate_layout.py ../2026-09-06.pptx     # must print OK
python3 $S/render_preview.py ../2026-09-06.pptx preview 90
```

## Shape

**Slides 1–14 are the talk.** 1–9 workload evidence, 10–13 this week's device
work, 14 the decision list.

**Slide 15 is a section divider; 16–85 are backup.** One slide per experimental
result in the session report — 31 figures (F1–F31) and 39 tables, each titled
with the question the experiment answered. Never presented in order; flipped to
on demand. Source: `appendix_slides.json`, merged into `deck.json` at build
time. Figures live in `figures/appendix/` and are verbatim copies — none was
redrawn, so the document-density ones (F21, F30, F31 especially) will not read
on a projector.

Note the builder's real table capacity is **5 rows, not 7**, once a two-line
title and a three-line subtitle are present. Sixteen appendix tables were
reshaped for it — rows selected with the omission named in the subtitle, one
restructured into columns, one split into "(1 of 2)". No row was dropped
silently.

## What this deck argues

Not a progress report. Three verdicts on where a wafer belongs in agentic
serving — where it fits, where it does not, and where it should fit but cannot
yet. Slides 1–9 are workload evidence; 10–15 are this week's device work;
16 is the decision list.

The spine: 96.2% of an agentic call's context is KV the decoder has already
seen, so the question is what it costs to put that back in front of the scan.
Three supply paths — stay resident, move it back, recompute it. This week made
"recompute" 5.7× faster; whether that matters at all turns on whether a host
KV mirror exists, which is unmeasured.

## Figures

| file | source | regenerate |
|---|---|---|
| `figures/kv_supply_paths.png` | **Excalidraw source of truth** at `wse3-performance-model/docs/diagrams/2026-09-06-kv-supply-paths.excalidraw` | `python3 wse3-performance-model/docs/diagrams/gen_kv_supply_paths.py`, then copy the PNG here |
| `figures/four_way_split.png` | data figure | `python3 figures/fig_four_way_split.py` (data inline, from the decomposition below) |

`figures/{kv_stride,vstack_topology,two_wafer_floorplan,phase_breakdown}.png`
are copies of project diagrams kept for reference. **They are not used in the
deck** — all four are document-density figures that are unreadable when
projected, so those slides became `metrics` instead. Do not put them back
without redrawing them at slide density.

## Data provenance

- Four-way decomposition, slides 2–4, 9: `wse3-performance-model/analyses/2026-09-06-kv-four-way-decomposition/`.
  Claude Code trace, 46,650 calls replayed in timestamp order against a
  512-token block LRU, **anyblock** scoring. The `leading` rule from
  `percall_latency.py` is unusable on this trace (median context exceeds every
  capacity; LRU evicts the head first, so median resident reads 0). Context
  medians: **196,590** over all calls including sidechains, **301,617**
  main-thread only — always say which.
- L ladder, vertical stacking: `docs/reports/2026-09-04-4b-wide-layer-session-report.md`,
  Rounds 77–116.

### Clock convention — changed 2026-09-07

Cycles are the measurement and are frequency-independent. **Every tok/s in this
deck is converted at 0.85 GHz** (`tok/s = 0.85e9 / cycles_per_token`), which is
Le's rule as of 2026-09-07 and what the launcher already prints. This
supersedes the earlier interim rule of quoting at 750 MHz; a figure taken from
the report at 750 MHz must be multiplied by **1.133**. Ratios — decoder versus
native prefill, rung versus rung, stacked versus side-by-side — are ratios of
cycle counts and do not move with the clock. Native prefill at 0.85 GHz is
10,545–11,143 tok/s.
- Two-wafer numbers: `docs/analysis/2026-09-03-4b-two-wafer-pp-decode-demo.md`.
- SRAM route table: `wse3-performance-model/demo/qwen3-4b-decode-sram/s1-init-route-table/README.md`.
  Uncommitted working copy; Le commits.

## Do not put these on a slide

Superseded or unsupportable, per the report's Round 116 corrections table and
the owning sessions:

- Any **GPU comparison**. Every H200 figure is an external number for a **9B**
  from the MeshRT paper; no 4B GPU curve has been measured, and Le expects a
  real one to come in 2–3× faster — which would move the 5% fit threshold and
  turn the "no thinking = parity" row into a loss.
- L = 4 as "P = 128, one lane" (128² is the L = 2 rung); "two lanes of
  256-wide blocks" (only one fits).
- The A1 stall as the queue-7 rebind (falsified by a controlled job); the B′
  wedge as the funnels (it was phantom strip cells); the probe wedge as
  cross-band transit (refuted by bisect).
- "Oracle overlap 1.000" as strong evidence — it measured sampling divergence.
  The real evidence is the byte-identity chain.
- 32 B per context position (47.9 measured); context cap = 127 × rows (true
  only before the stride lift).
- SRAM: the superseded **local**-compile figures (appliance figures only); the
  30,464 ceiling as demonstrated context (it is a compile-sweep link ceiling,
  never executed); the `--shared-reduce-len` change folded in as if free (it
  costs +0.39%).
- Two wafers: "+16% step" (it prices one crossing where the layout makes two);
  171/175 µs (n=1 and n=2 — the n=3 mean is 172, quote "≈170").

## Labelled projections, not measurements

Stacked-layout numbers beyond the measured three-layer rig (the 1.34× second
lane); post-lift context ceilings other than L = 1's 12,032 (model, not
compile); the two-wafer net benefit (measured cost, measured token shift, but
the reload path is deliberately left unpriced because that link is unmeasured).
