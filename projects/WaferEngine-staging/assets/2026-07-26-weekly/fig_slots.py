#!/usr/bin/env python3
"""Diagram: the M1-S0 contract — one number (bsz) split into slots and batch."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

INK, BODY, MUTED = "#18181B", "#52525B", "#A1A1AA"
VIOLET, BLUE, GREEN = "#6D28D9", "#1D4ED8", "#047857"
TV, TB, TG = "#F2EDFD", "#E9F0FE", "#E5F4EE"
F = "DejaVu Sans"

fig = plt.figure(figsize=(13.6, 5.0), dpi=210)
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, 100); ax.set_ylim(0, 37); ax.axis("off")

def box(x, y, w, h, fill, edge, lw=1.9, ls="solid"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.55",
                                fc=fill, ec=edge, lw=lw, linestyle=ls))

# ---------------- left: today --------------------------------------------
ax.text(1, 33.0, "Today", fontsize=16.5, color=INK, fontweight="bold", family=F)
ax.text(1, 30.2, "one number does both jobs", fontsize=12.5, color=MUTED, family=F)

for i in range(2):
    y = 22.0 - i * 6.6
    box(1, y, 16.5, 5.2, TV, VIOLET)
    ax.text(9.25, y + 2.6, f"request {i}", ha="center", va="center",
            fontsize=13, color=VIOLET, fontweight="bold", family=F)
ax.text(1, 12.2, "storage and compute are locked\ntogether: you can only keep as\nmany requests as you compute",
        ha="left", va="top", fontsize=12, color=BODY, family=F)

ax.plot([23.5, 23.5], [2, 35], color="#E4E4E7", lw=2)

# ---------------- right: M1 ----------------------------------------------
ax.text(28, 33.0, "M1", fontsize=16.5, color=INK, fontweight="bold", family=F)

SX, SW, BX, BW = 28, 16.5, 78, 16.5
MIDX = (SX + SW + BX) / 2

ax.text(SX, 28.6, "SLOTS  (S)", fontsize=14.5, color=GREEN, fontweight="bold", family=F)
ax.text(SX, 25.9, "kept resident", fontsize=12.5, color=MUTED, family=F)
ax.text(BX, 28.6, "BATCH  (M)", fontsize=14.5, color=BLUE, fontweight="bold", family=F)
ax.text(BX, 25.9, "computed this pass", fontsize=12.5, color=MUTED, family=F)
ax.text(MIDX, 28.6, "active_slot[ ]", ha="center", fontsize=14, color=VIOLET,
        fontweight="bold", family=F)
ax.text(MIDX, 25.9, "which slot each lane works on", ha="center",
        fontsize=12, color=MUTED, family=F)

slots = [("chat A", True), ("free", False), ("chat B", True)]
SLOT_Y = [18.4, 12.2, 6.0]
for i, (name, occ) in enumerate(slots):
    y = SLOT_Y[i]
    fill, edge, lw, ls = (TG, GREEN, 1.9, "solid") if occ else ("white", MUTED, 1.7, (0, (4, 3)))
    box(SX, y, SW, 5.0, fill, edge, lw, ls)
    ax.text(SX + SW / 2, y + 2.5, name, ha="center", va="center", fontsize=13,
            color=edge, fontweight=("bold" if occ else "normal"), family=F)
    ax.text(SX - 1.3, y + 2.5, str(i), ha="right", va="center",
            fontsize=12, color=MUTED, family=F)

for lane_y, src in [(16.4, 0), (7.4, 2)]:
    box(BX, lane_y, BW, 5.0, TB, BLUE)
    ax.text(BX + BW / 2, lane_y + 2.5, "lane " + ("0" if src == 0 else "1"),
            ha="center", va="center", fontsize=13, color=BLUE,
            fontweight="bold", family=F)
    ax.add_patch(FancyArrowPatch((SX + SW + 1.1, SLOT_Y[src] + 2.5),
                                 (BX - 1.1, lane_y + 2.5),
                                 arrowstyle="-|>", mutation_scale=18,
                                 color=VIOLET, lw=2.0,
                                 connectionstyle="arc3,rad=0.10"))

ax.text(SX, 2.9, "S ≥ M   —   the cache holds more requests than any single pass computes.",
        fontsize=13.5, color=INK, fontweight="bold", family=F)
ax.text(SX, 0.5, "Verified: with S = M the build is bit-identical to before, so the change landed switched off.",
        fontsize=12, color=BODY, family=F)

fig.savefig("/tmp/claude-1023/-home-lexu-WaferEngine-staging/a95262c6-8919-43d3-a293-b720d73d7eac/scratchpad/fig_slots.png",
            facecolor="white")
print("ok")
