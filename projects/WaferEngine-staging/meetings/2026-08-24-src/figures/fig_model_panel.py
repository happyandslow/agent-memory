#!/usr/bin/env python3
"""Slide-6 model panel: the three fitted equations + every coefficient,
value (task/dsd), meaning, and fit provenance. Internal-discussion style:
no hero numbers, dense but readable."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

fig = plt.figure(figsize=(13.2, 7.0))
ax = fig.add_axes([0, 0, 1, 1]); ax.axis("off")
ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.set_autoscale_on(False)
MONO = {"family": "DejaVu Sans Mono"}

# ---- equations block
ax.text(0.03, 0.965, "Fitted models (cycles; valid E ≥ 64 — E=4 sits in the floor regime; fwd = (N − N/R)·E)",
        fontsize=13.5, fontweight="bold")
eqs = [
    ("v3", "t = (245.4·N + 326)  +  (E−4)·N·(86.3 | 56.0)          +  2(D−1)·2.0", "#1e1e1e"),
    ("v4", "t = (61,058 | 78,676) + (E−4)·N·(96.00 | 65.08)  +  (1.06 | 1.29)·fwd", "#7048e8"),
    ("v5", "t = (70,561 | 70,076) + (E−4)·N·(87.87 | 57.00)  +  (30.7 | 47.0)·fwd  [+157k dsd,R>1]", "#2f9e44"),
]
for i, (tag, eq, col) in enumerate(eqs):
    y = 0.905 - i * 0.052
    ax.text(0.045, y, tag, fontsize=12.5, fontweight="bold", color=col)
    ax.text(0.085, y, eq, fontsize=12.5, color=col, **MONO)
ax.text(0.045, 0.905 - 3 * 0.052, "(pairs are task | dsd · floors fitted at N=256 · selftest: 39 device anchors, v3 0.89% / v5 0.83% / v4 0.23%)",
        fontsize=10.5, color="#666666")

# ---- coefficient table (3 columns; meaning + gray fit note)
rows = [
    ("floor  (per cycle)", "245.4\u00b7N + 326", "one-time work: per-row door-open flush chain + GO inject / join / fence landing",
     "fit: Exp-A E=4 cells, linear in N, max residual 8.8 ns"),
    ("marginal_v3", "86.3 | 56.0", "full-cycle cost per (word,PE): park 43.3 + reload share (owner task 43.0 \u2192 dsd emit 13.0)",
     "fit: payload sweep + Exp-A (\u221dN to 0.03%); dsd split by Exp-B"),
    ("marginal_v4", "96.00 | 65.08", "v3 + ~9.6 cyc/word: always-on role machinery (GO taps, switch writes) \u2014 paid even at R=1",
     "fit: 2-point solve on v4's own R=1 cells (E=64, 512)"),
    ("marginal_v5", "87.87 | 57.00", "v3 + ~1.6 cyc/word: cascade per-word branches that do not compile out at R=1 (H1 falsified)",
     "fit: 2-point solve on v5's own R=1 cells"),
    ("tax_v4  (/fwd word)", "1.06 | 1.29", "deeper bands transit shallower rows at ROUTER level \u2014 no CE ever touches the word",
     "fit: least squares over 8 measured deltas, residual \u2264 0.25%"),
    ("tax_v5  (/fwd word)", "30.7 | 47.0", "row-0 CE store-and-forwards every deeper word \u2014 a full data-task dispatch per word",
     "fit: \u0394-vs-fwd slopes across R\u2208{2,4} \u00d7 E\u2208{64,512}"),
    ("c_fwd_word", "75.4 \u00b1 0.9", "row-0 park receive+validate+re-emit; vs 43.3 receive-only \u21d2 forwarding is a second task, not an increment",
     "fit: park-span decomposition, 4 independent cells agree"),
    ("c_relay_word", "\u2248 28.8", "row-0 reload relay per word (the bare synchronous emit loop alone is 13.0)",
     "fit: tax_dsd identity; task-mode cross-check agrees to 1.6%"),
    ("dsd_strip_fill", "\u2248 157k cyc", "v5 dsd R>1 constant: strip rows emit their own block before relaying \u2014 fast owners expose it",
     "fit: \u0394-fit intercepts (153k / 162k)"),
    ("t_hop_router", "2.0 cyc/hop", "pure fabric transit per extra row of distance; no per-word term \u21d2 placement is latency-free",
     "fit: Exp-C, D \u2208 {8, 32}"),
]
y0, dy = 0.655, 0.0595
ax.text(0.03, y0 + 0.045, "coefficient", fontsize=11, fontweight="bold", color="#888888")
ax.text(0.245, y0 + 0.045, "value (task | dsd)", fontsize=11, fontweight="bold", color="#888888")
ax.text(0.415, y0 + 0.045, "what it measures \u00b7 how it was fit", fontsize=11, fontweight="bold", color="#888888")
ax.plot([0.03, 0.97], [y0 + 0.036] * 2, color="#cccccc", lw=1, transform=ax.transAxes)
for i, (name, val, meaning, fit) in enumerate(rows):
    y = y0 - i * dy
    if i % 2 == 0:
        ax.add_patch(plt.Rectangle((0.025, y - 0.036), 0.95, dy - 0.003,
                     transform=ax.transAxes, color="#f4f4f8", zorder=0))
    ax.text(0.03, y, name, fontsize=10.6, **MONO)
    ax.text(0.245, y, val, fontsize=10.6, fontweight="bold", **MONO)
    ax.text(0.415, y, meaning, fontsize=10.2)
    ax.text(0.415, y - 0.026, fit, fontsize=9.0, color="#777777")
fig.savefig(__file__.rsplit("/", 1)[0] + "/fig_model_panel.png", dpi=175)
print("model panel written")
