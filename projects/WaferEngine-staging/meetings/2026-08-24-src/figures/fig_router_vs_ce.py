#!/usr/bin/env python3
"""Render slide-7 content: define router-only and compare CE coefficients."""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyBboxPatch


HERE = Path(__file__).resolve().parent
OUT = HERE / "fig_router_vs_ce.png"

INK = "#18181B"
BODY = "#52525B"
MUTED = "#A1A1AA"
VIOLET = "#6D28D9"
BLUE = "#1D4ED8"
GREEN = "#047857"
RULE = "#E4E4E7"
CARD = "#F7F7F8"

plt.rcParams.update({"font.family": "Arimo"})

fig = plt.figure(figsize=(16, 6.2), dpi=180, facecolor="white")
gs = fig.add_gridspec(1, 2, width_ratios=[0.82, 1.18], wspace=0.28)
ax_l = fig.add_subplot(gs[0, 0])
ax_r = fig.add_subplot(gs[0, 1])
ax_l.set_axis_off()

ax_l.text(0.00, 0.96, "WHAT ‘ROUTER-ONLY’ MEANS", color=MUTED,
          fontsize=15, fontweight="bold", va="top", transform=ax_l.transAxes)
ax_l.text(0.00, 0.84, "Wavelet stays in the fabric switch",
          color=INK, fontsize=20, fontweight="bold", va="top",
          transform=ax_l.transAxes)

path_box = FancyBboxPatch((0.00, 0.58), 0.92, 0.18,
                          boxstyle="round,pad=0.018,rounding_size=0.02",
                          linewidth=1.2, edgecolor=BLUE, facecolor="#E9F0FE",
                          transform=ax_l.transAxes)
ax_l.add_patch(path_box)
ax_l.text(0.05, 0.69, "NORTH input  →  switch  →  SOUTH output",
          color=BLUE, fontsize=14.5, fontweight="bold", va="center",
          transform=ax_l.transAxes)
ax_l.text(0.05, 0.62, "no RAMP · no IQ/task · no CE · no local copy/re-emit",
          color=BODY, fontsize=11, va="center", transform=ax_l.transAxes)

ax_l.text(0.00, 0.49, "Measured router-only terms", color=INK,
          fontsize=16, fontweight="bold", va="top", transform=ax_l.transAxes)
ax_l.text(0.03, 0.40,
          "Distance latency\n"
          "  t_hop = 2.0 cycles/hop\n"
          "  round trip = 2(D-1)t_hop\n"
          "  +28 cycles at D=8; +124 at D=32",
          color=BODY, fontsize=12.2, linespacing=1.42, va="top",
          transform=ax_l.transAxes)
ax_l.text(0.03, 0.19,
          "Multi-row forwarding\n"
          "  v4 tax = 1.06 | 1.29 cycles/forwarded-word",
          color=BODY, fontsize=12.2, linespacing=1.42, va="top",
          transform=ax_l.transAxes)
ax_l.text(0.00, 0.02,
          "Still consumes fabric links and may backpressure.\n"
          "Current measurements are isolated, single-lane runs.",
          color=VIOLET, fontsize=10.5, fontweight="bold", va="bottom",
          transform=ax_l.transAxes)

labels = [
    "router fwd · task",
    "router fwd · DSD",
    "emit loop",
    "reload relay",
    "park receive",
    "receive + forward",
]
values = np.array([1.06, 1.29, 13.0, 28.8, 43.3, 75.4])
colors = [BLUE, BLUE, GREEN, GREEN, VIOLET, VIOLET]
y = np.arange(len(labels))
bars = ax_r.barh(y, values, color=colors, alpha=0.88, height=0.58)
ax_r.set_yticks(y, labels, fontsize=11.5, color=INK)
ax_r.invert_yaxis()
ax_r.set_xlim(0, 82)
ax_r.set_xlabel("measured coefficient (cycles / word)", fontsize=12,
                color=BODY)
ax_r.set_title("Measured per-word coefficients",
               loc="left", fontsize=18, fontweight="bold", color=INK, pad=26)
ax_r.text(0.99, 1.02, "CE terms are 10–71× the v4 router coefficient",
          transform=ax_r.transAxes, ha="right", va="bottom", color=VIOLET,
          fontsize=11.5, fontweight="bold")
ax_r.grid(axis="x", color=RULE, linewidth=0.8)
ax_r.set_axisbelow(True)
for spine in ax_r.spines.values():
    spine.set_visible(False)
ax_r.tick_params(axis="x", colors=BODY, labelsize=11)
for bar, value in zip(bars, values):
    ax_r.text(value + 1.1, bar.get_y() + bar.get_height()/2,
              f"{value:g}", va="center", ha="left", fontsize=12,
              color=INK, fontweight="bold")
ax_r.axvspan(0, 2.5, color="#E9F0FE", alpha=0.6, zorder=0)

fig.savefig(OUT, bbox_inches="tight", pad_inches=0.04, facecolor="white")
print(OUT)
