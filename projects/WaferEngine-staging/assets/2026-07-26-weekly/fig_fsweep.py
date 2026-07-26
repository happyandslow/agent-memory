#!/usr/bin/env python3
"""F-sweep: cost per token falls by a constant amount per forced step (simulator)."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

INK, BODY, MUTED = "#18181B", "#52525B", "#A1A1AA"
VIOLET, GREEN = "#6D28D9", "#047857"
F = "DejaVu Sans"

# milestones/M0-reuse-foundation.md:435-442  (test_sim_2x2blk_fsweep_F{1,2,4,6})
pts = [(0, 17138.0, "F=1"), (0, 17137.2, "F=2"), (2, 13096.4, "F=4"), (4, 8930.6, "F=6")]

fig, ax = plt.subplots(figsize=(13.6, 5.4), dpi=210)

xs = [0, 4.4]
ax.plot(xs, [17138 - 2040 * x for x in xs], color=MUTED, lw=2, ls=(0, (5, 4)), zorder=1)
ax.text(2.35, 16350, "fit:   17138  −  2040 × forced steps",
        fontsize=14, color=MUTED, family=F)

for x, y, lab in pts:
    ax.scatter([x], [y], s=190, color=VIOLET, zorder=3, edgecolor="white", lw=2)
for x, y, lab in [(0, 17138.0, "F = 1, 2"), (2, 13096.4, "F = 4"), (4, 8930.6, "F = 6")]:
    ax.annotate(lab, (x, y), textcoords="offset points", xytext=(16, 12),
                fontsize=14, color=INK, fontweight="bold", family=F)

ax.set_xlabel("forced decode steps inside the timed window", fontsize=14.5,
              color=BODY, family=F, labelpad=10)
ax.set_ylabel("cycles per token", fontsize=14.5, color=BODY, family=F, labelpad=10)
ax.set_xlim(-0.45, 4.9)
ax.set_ylim(7200, 18700)
ax.set_xticks([0, 1, 2, 3, 4])
ax.tick_params(labelsize=13, colors=BODY)
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
for s in ("left", "bottom"):
    ax.spines[s].set_color("#E4E4E7")
ax.grid(axis="y", color="#F1F1F3", lw=1.2)
ax.set_axisbelow(True)

plt.tight_layout()
plt.savefig("/tmp/claude-1023/-home-lexu-WaferEngine-staging/a95262c6-8919-43d3-a293-b720d73d7eac/scratchpad/fig_fsweep.png",
            bbox_inches="tight", facecolor="white")
print("ok")
