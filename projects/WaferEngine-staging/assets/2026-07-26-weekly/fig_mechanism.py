#!/usr/bin/env python3
"""Diagram: the two ways a forced decode step could be cheaper."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

INK, BODY, MUTED = "#18181B", "#52525B", "#A1A1AA"
VIOLET, BLUE, GREEN, AMBER = "#6D28D9", "#1D4ED8", "#047857", "#B45309"
TV, TB, TA, GHOST = "#F2EDFD", "#E9F0FE", "#FDF3E3", "#EDEDF0"
F = "DejaVu Sans"

fig = plt.figure(figsize=(13.6, 5.0), dpi=210)
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, 100); ax.set_ylim(0, 37); ax.axis("off")

X0 = 26.0
HEAD, BLK, TAIL = 3.2, 11.8, 7.5

def seg(x, y, w, h, fill, edge, label, fs):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.4",
                                fc=fill, ec=edge, lw=1.6))
    ax.text(x + w / 2, y + h / 2, label, ha="center", va="center",
            fontsize=fs, color=edge, fontweight="bold", family=F)

def step(x, y, h, with_tail=True, ghost=False, fs=11.5):
    seg(x, y, HEAD, h, GHOST if ghost else TV, MUTED if ghost else VIOLET, "in", fs)
    seg(x + HEAD, y, BLK, h, GHOST if ghost else TB, MUTED if ghost else BLUE, "28 layers", fs)
    if with_tail:
        seg(x + HEAD + BLK, y, TAIL, h, TA, AMBER, "pick token", fs)
    return x + HEAD + BLK + (TAIL if with_tail else 0)

def rowlabel(ytag, ynote, tag, note, color=INK):
    ax.text(0.5, ytag, tag, fontsize=13.5, color=color, fontweight="bold",
            va="center", family=F)
    ax.text(0.5, ynote, note, fontsize=11.5, color=MUTED, va="center", family=F)

ax.text(0.5, 35.4, "The measurement says it is the first one.",
        fontsize=13, color=INK, family=F)

# ---------- row 1: plain decode ------------------------------------------
Y1, H1 = 27.6, 5.4
rowlabel(31.2, 28.2, "Plain decode", "each step picks its own token")
x = X0
for _ in range(3):
    x = step(x, Y1, H1)
PLAIN_END = x

a = X0 + HEAD + BLK + TAIL * 0.5
b = X0 + HEAD + BLK + TAIL + HEAD * 0.5
ax.add_patch(FancyArrowPatch((a, Y1), (b, Y1), arrowstyle="-|>", mutation_scale=14,
                             color=AMBER, lw=1.9, connectionstyle="arc3,rad=-0.9"))
ax.text(X0, 24.8,
        "the next token only exists once the picking finishes, so nothing can start early",
        fontsize=11.5, color=AMBER, family=F, va="center")

# ---------- row 2: skip-compute ------------------------------------------
Y2, H2 = 15.0, 5.4
rowlabel(18.6, 15.6, "1.  Skip the picking", "the token is already known", GREEN)
x = X0
for _ in range(3):
    x = step(x, Y2, H2, with_tail=False)
SKIP_END = x

ax.annotate("", xy=(SKIP_END, Y2 + H2 / 2), xytext=(PLAIN_END, Y2 + H2 / 2),
            arrowprops=dict(arrowstyle="<->", color=GREEN, lw=2))
ax.text((SKIP_END + PLAIN_END) / 2, 21.8, "time saved", ha="center",
        fontsize=12.5, color=GREEN, fontweight="bold", family=F)

# ---------- row 3: pipelining (staggered) --------------------------------
LANES, H3, OV = [6.2, 3.4, 0.6], 2.6, 9.0
rowlabel(6.5, 3.6, "2.  Overlap the steps", "nothing left to wait for", MUTED)
for i, ly in enumerate(LANES):
    step(X0 + i * OV, ly, H3, with_tail=False, ghost=True, fs=9.5)
PIPE_END = X0 + (len(LANES) - 1) * OV + HEAD + BLK

ax.annotate("", xy=(PIPE_END, LANES[1] + H3 / 2), xytext=(SKIP_END, LANES[1] + H3 / 2),
            arrowprops=dict(arrowstyle="<->", color=MUTED, lw=1.8, linestyle=(0, (4, 3))))
ax.text((PIPE_END + SKIP_END) / 2, 9.6, "extra gain  —  not seen at this scale",
        ha="center", fontsize=12.5, color=MUTED, fontweight="bold", family=F)

fig.savefig("/tmp/claude-1023/-home-lexu-WaferEngine-staging/a95262c6-8919-43d3-a293-b720d73d7eac/scratchpad/fig_mechanism.png",
            facecolor="white")
print("ok")
