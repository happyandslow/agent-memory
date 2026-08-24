#!/usr/bin/env python3
"""Multirow delta vs forwarded words: both designs, same law, 25-35x coefficients."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

FWD = np.array([8192, 12288, 65536, 98304])
D = {  # measured deltas vs each design's own R=1 (cycles)
    ("v5", "task"): [255083, 392282, 1967594, 3112277],
    ("v5", "dsd"):  [539939, 741477, 3186686, 4860798],
    ("v4", "task"): [9026, 14935, 66369, 100949],
    ("v4", "dsd"):  [10162, 18349, 76915, 132592],
}
FIT = {("v5", "task"): lambda f: 30.7 * f,
       ("v5", "dsd"):  lambda f: 47.0 * f + 157_000,
       ("v4", "task"): lambda f: 1.06 * f,
       ("v4", "dsd"):  lambda f: 1.29 * f}
COL = {"v5": "#2f9e44", "v4": "#7048e8"}

fig, ax = plt.subplots(figsize=(11.6, 6.2))
ax.set_facecolor("#fafafa")
fs = np.geomspace(6000, 130000, 100)
for (design, mode), ys in D.items():
    ls = "-" if mode == "task" else "--"
    mk = "o" if mode == "task" else "s"
    ax.plot(fs, [FIT[(design, mode)](f) for f in fs], ls=ls, color=COL[design], lw=2.4,
            label=f"{design} {mode}:  " + ("tax = 30.7 c/w" if (design, mode) == ("v5", "task")
                  else "tax = 47.0 c/w + 157k" if (design, mode) == ("v5", "dsd")
                  else "tax = 1.06 c/w" if (design, mode) == ("v4", "task") else "tax = 1.29 c/w"))
    ax.scatter(FWD, ys, color=COL[design], marker=mk, s=80, zorder=5,
               edgecolors="white", linewidths=0.8)
ax.annotate("v5 · CE store-and-forward", xy=(30000, 1.35e6), color="#2f9e44",
            fontsize=13, fontweight="bold")
ax.annotate("v4 · router transit\n(near wire speed)", xy=(30000, 2.1e4), color="#7048e8",
            fontsize=13, fontweight="bold")
ax.annotate("same linear law\n25–35× apart", xy=(90000, 4.1e5), fontsize=13,
            fontweight="bold", ha="center")
ax.set_xscale("log"); ax.set_yscale("log")
ax.set_xlabel("forwarded words  =  (N − N/R) · E", fontsize=13)
ax.set_ylabel("multi-row delta vs own R=1 (cycles)", fontsize=13)
ax.set_title("Both designs: Δ = tax × forwarded words — the coefficient is the mechanism",
             fontsize=16, fontweight="bold", loc="left", pad=12)
ax.grid(True, which="both", color="#e0e0e0", lw=0.6)
ax.legend(fontsize=11, loc="lower right", framealpha=0.95)
for sp in ("top", "right"):
    ax.spines[sp].set_visible(False)
fig.tight_layout()
fig.savefig(__file__.rsplit("/", 1)[0] + "/fig_samelaw.png", dpi=170)
print("samelaw fig written")
