#!/usr/bin/env python3
"""Four-way KV budget of an agentic call vs on-chip capacity C.

Data: analyses/2026-09-06-kv-four-way-decomposition/ (Claude Code trace,
46,650 calls replayed in timestamp order against a 512-token block LRU,
anyblock scoring). Values are the median over calls of that call's own
share of context, so the three categories are per-category medians and do
not sum to exactly 100% -- stated in the figure note rather than rescaled.
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

# wafer-slides design tokens (scripts/wafer_theme.py) -- do not invent new ones
INK = "#18181B"
BODY = "#52525B"
MUTED = "#A1A1AA"
ACCENT = "#6D28D9"
BLUE = "#1D4ED8"
GREEN = "#047857"

# C, resident %, reload %, new_prefill %  -- medians, anyblock scoring
ROWS = [
    ("167,000",           51.04, 39.27, 0.93),
    ("95,000",            27.25, 66.92, 0.93),
    ("51,200",            13.83, 82.35, 0.93),
    ("29,184  · today",    7.65, 89.44, 0.93),
    ("12,032",             2.96, 94.96, 0.93),
]

fig, ax = plt.subplots(figsize=(12.4, 5.2), dpi=200)
fig.patch.set_facecolor("white")
ax.set_facecolor("white")

h = 0.62
for i, (label, res, rel, new) in enumerate(ROWS):
    today = "today" in label
    ax.barh(i, res, height=h, color=GREEN, zorder=3)
    ax.barh(i, rel, height=h, left=res, color=BLUE, alpha=0.30, zorder=3)
    ax.barh(i, new, height=h, left=res + rel, color=ACCENT, zorder=4)

    if res >= 6:
        ax.text(res / 2, i, f"{res:.1f}%", ha="center", va="center",
                color="white", fontsize=11.5, fontweight="bold", zorder=5)
    else:
        # too narrow to letter inside; place it just past the segment
        ax.text(res + 1.2, i - 0.30, f"{res:.1f}%", ha="left", va="center",
                color=GREEN, fontsize=11, fontweight="bold", zorder=5)
    ax.text(res + rel / 2, i, f"{rel:.1f}%", ha="center", va="center",
            color=INK, fontsize=11.5, fontweight="bold", zorder=5)

    weight = "bold" if today else "normal"
    ax.text(-1.5, i, label, ha="right", va="center",
            color=INK if today else BODY, fontsize=12, fontweight=weight)

# the one number the slide is about
new_x = ROWS[3][1] + ROWS[3][2]
ax.annotate(
    "0.93% genuinely new\ninvariant in C",
    xy=(new_x + 0.5, 3), xytext=(new_x + 9, 3.9),
    color=ACCENT, fontsize=12.5, fontweight="bold", ha="left", va="center",
    arrowprops=dict(arrowstyle="-", color=ACCENT, lw=1.4,
                    connectionstyle="angle3,angleA=0,angleB=70"),
)

ax.set_yticks([])
ax.set_xlim(0, 104)
ax.set_ylim(-0.75, len(ROWS) - 0.05)
ax.set_xlabel("share of the median call's context", color=BODY, fontsize=12,
              labelpad=9)
ax.tick_params(axis="x", colors=MUTED, labelsize=11)
for s in ("top", "right", "left"):
    ax.spines[s].set_visible(False)
ax.spines["bottom"].set_color("#E4E4E7")
ax.xaxis.grid(True, color="#F4F4F5", lw=1, zorder=0)
ax.set_axisbelow(True)

ax.text(-1.5, len(ROWS) - 0.45, "on-chip KV capacity C, tokens",
        ha="right", va="center", color=MUTED, fontsize=11.5)

ax.legend(
    handles=[
        Patch(facecolor=GREEN, label="resident — re-used prefix still on chip (free)"),
        Patch(facecolor=BLUE, alpha=0.30,
              label="reload — re-used prefix evicted (movement, not recompute)"),
        Patch(facecolor=ACCENT, label="new prefill — never seen (must be computed)"),
    ],
    loc="lower center", bbox_to_anchor=(0.5, -0.30), ncol=3,
    frameon=False, fontsize=11.5, labelcolor=BODY, handlelength=1.5,
)

fig.text(0.5, -0.055,
         "Claude Code, 46,650 calls, 512-token block LRU, anyblock scoring. "
         "Per-category medians, so rows do not sum to exactly 100%.",
         ha="center", color=MUTED, fontsize=10.5)

fig.tight_layout()
fig.savefig("four_way_split.png", bbox_inches="tight", facecolor="white",
            pad_inches=0.30)
print("wrote four_way_split.png")
