#!/usr/bin/env python3
"""Diagram: what retain + force-decode does to a second-turn prompt."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

INK, BODY, MUTED = "#18181B", "#52525B", "#A1A1AA"
VIOLET, BLUE, GREEN, AMBER = "#6D28D9", "#1D4ED8", "#047857", "#B45309"
TV, TB, TG, TA = "#F2EDFD", "#E9F0FE", "#E5F4EE", "#FDF3E3"
F = "DejaVu Sans"

fig = plt.figure(figsize=(13.6, 5.0), dpi=210)
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, 100); ax.set_ylim(0, 37); ax.axis("off")

def bar(x, y, w, h, fill, edge, label, sub=None):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.55",
                                fc=fill, ec=edge, lw=1.9))
    ax.text(x + w / 2, y + h / 2 + (1.25 if sub else 0), label, ha="center", va="center",
            fontsize=15.5, color=edge, fontweight="bold", family=F)
    if sub:
        ax.text(x + w / 2, y + h / 2 - 2.05, sub, ha="center", va="center",
                fontsize=12.5, color=BODY, family=F)

def lane(y, tag, note):
    ax.text(0.8, y + 4.7, tag, fontsize=15, color=INK, fontweight="bold",
            va="center", family=F)
    ax.text(0.8, y + 1.9, note, fontsize=12, color=MUTED, va="center", family=F)

X0, W, H = 24, 75.5, 7.4

lane(25.6, "Turn 1", "prompt in, answer out")
bar(X0, 25.6, W * 0.46, H, TV, VIOLET, "prefill the prompt", "KV written to the cache")
bar(X0 + W * 0.46 + 0.9, 25.6, W * 0.54 - 0.9, H, TB, BLUE, "free decode",
    "one sampled token per step")

lane(14.2, "Turn 2  ·  no reuse", "today: the KV is thrown away")
bar(X0, 14.2, W * 0.72, H, "#F4F4F5", BODY, "prefill the WHOLE prompt again",
    "turn-1 text is re-read from token 0")
bar(X0 + W * 0.72 + 0.9, 14.2, W * 0.28 - 0.9, H, TB, BLUE, "free decode", None)

lane(2.8, "Turn 2  ·  with reuse", "what now works")
bar(X0, 2.8, W * 0.46, H, TG, GREEN, "reuse the resident KV", "no work at all")
bar(X0 + W * 0.46 + 0.9, 2.8, W * 0.26 - 0.9, H, TA, AMBER, "force-decode",
    "tokens given, not sampled")
bar(X0 + W * 0.72 + 0.9, 2.8, W * 0.28 - 0.9, H, TB, BLUE, "free decode", None)

ax.annotate("", xy=(X0, 11.6), xytext=(X0 + W * 0.46, 11.6),
            arrowprops=dict(arrowstyle="<->", color=GREEN, lw=2))
ax.text(X0 + W * 0.23, 12.3, "work that disappears", ha="center", va="bottom",
        fontsize=13.5, color=GREEN, fontweight="bold", family=F)

ax.text(X0, 34.4, "The prompt of turn 2 is the prompt of turn 1 plus new text",
        fontsize=13, color=MUTED, family=F)

fig.savefig("/tmp/claude-1023/-home-lexu-WaferEngine-staging/a95262c6-8919-43d3-a293-b720d73d7eac/scratchpad/fig_forcedecode.png",
            facecolor="white")
print("ok")
