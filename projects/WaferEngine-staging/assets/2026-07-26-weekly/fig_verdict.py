#!/usr/bin/env python3
"""The new force-decode verdict: at real scale the win is pipelining.

Left  panel: real WSE-3 context sweep (agent-memory assets/analyze_sweep.py output)
             prefill 256/768/1792/3840, F=1 vs F=209, 524,288 PEs, dim 2048,
             28 layers over 8 blocks (max 4 layers/block), vocab 151,936.
Right panel: simulator depth ablation, test_sim_abl_nb{2,4,8}_F{1,6}.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

INK, BODY, MUTED = "#18181B", "#52525B", "#A1A1AA"
VIOLET, BLUE, GREEN, AMBER = "#6D28D9", "#1D4ED8", "#047857", "#B45309"
F = "DejaVu Sans"

# --- device sweep --------------------------------------------------------
CTX = [256, 768, 1792, 3840]
RATIO = [11.7, 11.7, 11.8, 12.0]
PIPE_PRED = 100 * 4 / 28          # max layers per block / total layers

# --- sim block-count ablation (milestones/M0-reuse-foundation.md, 2026-07-27)
#     n_layers = 8 held FIXED; only the block grid changes.
ABL_LABEL = ["2 blocks\n4 layers each", "4 blocks\n2 layers each", "8 blocks\n1 layer each"]
ABL_MEAS = [100 * 47060 / 96835, 100 * 24134 / 97106, 100 * 12722 / 98285]
ABL_PRED = [50.0, 25.0, 12.5]

fig, (axL, axR) = plt.subplots(
    1, 2, figsize=(14.7, 5.0), dpi=210,
    gridspec_kw={"width_ratios": [1.45, 1.0], "wspace": 0.24})

def style(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color("#E4E4E7")
    ax.grid(axis="y", color="#F1F1F3", lw=1.2)
    ax.set_axisbelow(True)
    ax.tick_params(labelsize=12, colors=BODY)

# ============ LEFT: the discriminator ====================================
x = range(len(CTX))
axL.axhspan(PIPE_PRED - 1.6, PIPE_PRED + 1.6, color="#E5F4EE", zorder=0)
axL.axhline(PIPE_PRED, color=GREEN, lw=1.8, ls=(0, (5, 4)), zorder=1)
axL.text(2.62, PIPE_PRED + 3.0, "what overlap predicts:  4 of 28 layers",
         fontsize=12, color=GREEN, ha="right", family=F)

axL.plot(x, RATIO, color=VIOLET, lw=2.4, marker="o", ms=11,
         markeredgecolor="white", markeredgewidth=2, zorder=3)
for xi, r in zip(x, RATIO):
    axL.annotate(f"{r:.1f}%", (xi, r), textcoords="offset points",
                 xytext=(0, -26), ha="center", fontsize=12.5,
                 color=VIOLET, fontweight="bold", family=F)

axL.annotate("", xy=(2.05, 92), xytext=(2.05, 34),
             arrowprops=dict(arrowstyle="-|>", mutation_scale=18,
                             color=MUTED, lw=2, ls=(0, (4, 3))))
axL.text(1.92, 63, "skipped work would\nsend it climbing\ntoward 100%",
         fontsize=12, color=MUTED, ha="right", va="center", family=F)

axL.set_xticks(list(x)); axL.set_xticklabels([f"{c:,}" for c in CTX])
axL.set_xlim(-0.35, 3.35); axL.set_ylim(0, 104)
axL.set_yticks([0, 25, 50, 75, 100])
axL.set_yticklabels(["0", "25%", "50%", "75%", "100%"])
axL.set_xlabel("context length (tokens)", fontsize=13, color=BODY,
               family=F, labelpad=9)
axL.set_ylabel("cost of a forced token,\nas a share of a plain one",
               fontsize=13, color=BODY, family=F, labelpad=9)
axL.set_title("Real WSE-3  —  flat across a 15x context range",
              fontsize=14.5, color=INK, fontweight="bold", family=F,
              loc="left", pad=14)
style(axL)

# ============ RIGHT: the formula predicts it ==============================
xr = range(len(ABL_PRED))
axR.plot(xr, ABL_PRED, color=GREEN, lw=2.0, ls=(0, (5, 4)), marker="s", ms=10,
         markerfacecolor="white", markeredgewidth=2, zorder=2)
axR.plot(xr, ABL_MEAS, color=VIOLET, lw=2.4, marker="o", ms=11,
         markeredgecolor="white", markeredgewidth=2, zorder=3)
for xi, r in zip(xr, ABL_MEAS):
    axR.annotate(f"{r:.1f}%", (xi, r), textcoords="offset points",
                 xytext=(13, 6), fontsize=12.5, color=VIOLET,
                 fontweight="bold", family=F)
axR.text(0.10, 68, "predicted by overlap", fontsize=12, color=GREEN, family=F)
axR.text(0.10, 61, "measured", fontsize=12, color=VIOLET, fontweight="bold", family=F)

axR.set_xticks(list(xr)); axR.set_xticklabels(ABL_LABEL, fontsize=11.5)
axR.set_xlim(-0.3, 2.3); axR.set_ylim(0, 104)
axR.set_yticks([0, 25, 50, 75, 100])
axR.set_yticklabels(["0", "25%", "50%", "75%", "100%"])
axR.set_xlabel("same model, spread over more blocks", fontsize=13,
               color=BODY, family=F, labelpad=9)
axR.set_title("Simulator  —  the formula lands on the nose",
              fontsize=14.5, color=INK, fontweight="bold", family=F,
              loc="left", pad=14)
style(axR)

fig.savefig("/tmp/claude-1023/-home-lexu-WaferEngine-staging/a95262c6-8919-43d3-a293-b720d73d7eac/scratchpad/fig_verdict.png",
            facecolor="white", bbox_inches="tight")
print("ok")
