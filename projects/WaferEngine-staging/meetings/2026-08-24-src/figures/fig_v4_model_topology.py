#!/usr/bin/env python3
"""Render slide-6 content: v4 model form, fitted coefficients, and topology.

The topology panel is a crop of the v4 half of v4_vs_v5.png. Its editable
source of truth is WaferEngine-staging/docs/diagrams/
m3-multirow-v4-vs-v5.excalidraw.
"""

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from PIL import Image


HERE = Path(__file__).resolve().parent
OUT = HERE / "fig_v4_model_topology.png"

INK = "#18181B"
BODY = "#52525B"
MUTED = "#A1A1AA"
VIOLET = "#6D28D9"
BLUE = "#1D4ED8"
GREEN = "#047857"
RULE = "#E4E4E7"
CARD = "#F7F7F8"

plt.rcParams.update({"font.family": "Arimo", "mathtext.fontset": "dejavusans"})

fig = plt.figure(figsize=(16, 6.4), dpi=180, facecolor="white")
gs = fig.add_gridspec(1, 2, width_ratios=[1.12, 0.88], wspace=0.05)
ax_l = fig.add_subplot(gs[0, 0])
ax_r = fig.add_subplot(gs[0, 1])
for ax in (ax_l, ax_r):
    ax.set_axis_off()

ax_l.text(0.00, 0.96, "1 · MODEL FORM", color=MUTED, fontsize=15,
          fontweight="bold", va="top", transform=ax_l.transAxes)
ax_l.text(0.00, 0.86,
          r"$C_{v4}(N,E,R,m)=C_{floor}^{(m)}$"
          "\n" r"$\quad +(E-4)N\,C_{owner}^{(m)}$"
          "\n" r"$\quad +W_{fwd}(N,E,R)\,C_{router}^{(m)}$",
          color=INK, fontsize=22, linespacing=1.45, va="top",
          transform=ax_l.transAxes)
ax_l.text(0.00, 0.55,
          r"$W_{fwd}=(N-N/R)E,\qquad m\in\{task,DSD\}$",
          color=VIOLET, fontsize=17, va="top", transform=ax_l.transAxes)
ax_l.text(0.00, 0.48,
          "N = compute PEs/column · E = u32 words/PE · R = storage rows",
          color=BODY, fontsize=12.5, va="top", transform=ax_l.transAxes)

ax_l.text(0.00, 0.38, "2 · FITTED COEFFICIENTS", color=MUTED, fontsize=15,
          fontweight="bold", va="top", transform=ax_l.transAxes)

card = FancyBboxPatch((0.00, 0.02), 0.97, 0.31,
                      boxstyle="round,pad=0.012,rounding_size=0.018",
                      linewidth=1.0, edgecolor=RULE, facecolor=CARD,
                      transform=ax_l.transAxes)
ax_l.add_patch(card)

x = [0.035, 0.36, 0.54, 0.70]
headers = ["term", "task", "owner DSD", "physical role"]
for xpos, label in zip(x, headers):
    ax_l.text(xpos, 0.285, label.upper(), color=MUTED, fontsize=10.5,
              fontweight="bold", va="top", transform=ax_l.transAxes)

rows = [
    (r"$C_{floor}$", "61,058", "78,676", "launch/control + role setup"),
    (r"$C_{owner}$", "96.00", "65.08", "endpoint payload, cyc/word"),
    (r"$C_{router}$", "1.06", "1.29", "router-only fwd, cyc/word"),
]
ys = [0.215, 0.145, 0.075]
colors = [INK, BLUE, VIOLET]
for y, row, color in zip(ys, rows, colors):
    ax_l.text(x[0], y, row[0], color=color, fontsize=13.5,
              fontweight="bold", va="top", transform=ax_l.transAxes)
    ax_l.text(x[1], y, row[1], color=INK, fontsize=13.5,
              va="top", transform=ax_l.transAxes)
    ax_l.text(x[2], y, row[2], color=INK, fontsize=13.5,
              va="top", transform=ax_l.transAxes)
    ax_l.text(x[3], y, row[3], color=BODY, fontsize=11.5,
              va="top", transform=ax_l.transAxes)

image = Image.open(HERE / "v4_vs_v5.png").convert("RGB")
w, h = image.size
# Keep the v4 panel only; the full editable source remains the source of truth.
crop = image.crop((100, 82, int(w * 0.485), int(h * 0.90)))
ax_r.imshow(crop, extent=(0.00, 1.00, 0.01, 0.99), aspect="auto")

fig.savefig(OUT, bbox_inches="tight", pad_inches=0.04, facecolor="white")
print(OUT)
