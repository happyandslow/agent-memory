"""Generate the C1 ragged-lane CS-3 result graphic for the weekly deck."""

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import numpy as np


OUTPUT_DIR = Path(__file__).resolve().parents[1] / "figures"
K = np.array([0, 256, 512, 768])
AVOIDED_WORK_PERCENT = np.array([0.0, 12.46, 24.98, 37.49])
MEAN_RAW_CYCLES = np.array([288953017.6, 289047867.4, 289220357.6, 289038838.6])
SPEEDUP_VS_MATCHED_K0_PERCENT = np.array([0.0, -0.0328, -0.0924, -0.0297])


def add_value_labels(axis, xs, ys, fmt, offset=0.8):
    for x, y in zip(xs, ys, strict=True):
        axis.annotate(fmt.format(y), (x, y), xytext=(0, offset),
                      textcoords="offset points", ha="center", va="bottom",
                      fontsize=10, fontweight="bold", color="#172033")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "font.size": 11,
        "axes.titleweight": "bold",
        "axes.labelcolor": "#334155",
        "xtick.color": "#475569",
        "ytick.color": "#475569",
    })
    figure = plt.figure(figsize=(14.4, 8.1), facecolor="white")
    grid = figure.add_gridspec(
        2, 2, height_ratios=[3.2, 1.3], width_ratios=[1.2, 1],
        left=0.07, right=0.98, top=0.96, bottom=0.07, hspace=0.30, wspace=0.12,
    )
    ax_speedup = figure.add_subplot(grid[0, 0])
    ax_avoided = figure.add_subplot(grid[0, 1])
    ax_cycles = figure.add_subplot(grid[1, :])

    bars = ax_speedup.bar(K, SPEEDUP_VS_MATCHED_K0_PERCENT, width=165,
                          color=["#94a3b8", "#c2410c", "#c2410c", "#c2410c"], zorder=3)
    ax_speedup.axhline(0, color="#172033", linewidth=1.8, zorder=4, label="zero-speedup reference")
    ax_speedup.set_title("Measured speedup vs. matched K=0", loc="left", fontsize=14)
    ax_speedup.set_ylabel("Speedup (%)")
    ax_speedup.set_xlabel("Inactive-lane work K")
    ax_speedup.set_xticks(K)
    ax_speedup.set_ylim(-0.115, 0.025)
    ax_speedup.grid(axis="y", color="#e2e8f0", linewidth=1, zorder=0)
    ax_speedup.spines[["top", "right"]].set_visible(False)
    ax_speedup.legend(loc="lower left", frameon=False, fontsize=9)
    add_value_labels(ax_speedup, K, SPEEDUP_VS_MATCHED_K0_PERCENT, "{:.4f}%", offset=-16)
    ax_speedup.text(0.035, 0.18, "All nonzero K cases are\nslightly negative.", transform=ax_speedup.transAxes,
                    fontsize=12, fontweight="bold", color="#9a3412",
                    bbox={"boxstyle": "round,pad=0.45", "facecolor": "#fff7ed", "edgecolor": "#fdba74"})

    ax_avoided.plot(K, AVOIDED_WORK_PERCENT, marker="o", markersize=8, linewidth=3,
                    color="#15803d", zorder=3)
    ax_avoided.fill_between(K, AVOIDED_WORK_PERCENT, color="#bbf7d0", alpha=0.55, zorder=2)
    ax_avoided.set_title("Timed avoided lane work rises", loc="left", fontsize=14)
    ax_avoided.set_ylabel("Avoided work (%)")
    ax_avoided.set_xlabel("Inactive-lane work K")
    ax_avoided.set_xticks(K)
    ax_avoided.set_ylim(0, 43)
    ax_avoided.grid(axis="y", color="#e2e8f0", linewidth=1, zorder=0)
    ax_avoided.spines[["top", "right"]].set_visible(False)
    add_value_labels(ax_avoided, K, AVOIDED_WORK_PERCENT, "{:.2f}%")
    ax_avoided.annotate("37.49% avoided work\n→ −0.0297% speedup", xy=(768, 37.49), xytext=(500, 30),
                        arrowprops={"arrowstyle": "->", "color": "#166534", "lw": 1.4},
                        bbox={"boxstyle": "round,pad=0.4", "facecolor": "#f0fdf4", "edgecolor": "#86efac"},
                        fontsize=10.5, fontweight="bold", color="#166534")

    ax_cycles.plot(K, MEAN_RAW_CYCLES, marker="o", markersize=7, linewidth=2.5, color="#334155")
    ax_cycles.set_title("Mean raw cycles (TSC)", loc="left", fontsize=13)
    ax_cycles.set_ylabel("Raw cycles")
    ax_cycles.set_xlabel("Inactive-lane work K")
    ax_cycles.set_xticks(K)
    ax_cycles.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value / 1e6:.2f}M"))
    ax_cycles.grid(axis="y", color="#e2e8f0", linewidth=1)
    ax_cycles.spines[["top", "right"]].set_visible(False)
    ax_cycles.text(0.015, 0.12, "Exact range: 288,953,017.6–289,220,357.6 raw cycles", transform=ax_cycles.transAxes,
                   fontsize=10.5, color="#334155", bbox={"boxstyle": "round,pad=0.35", "facecolor": "#f8fafc", "edgecolor": "#cbd5e1"})

    for extension in ("png", "svg"):
        figure.savefig(OUTPUT_DIR / f"c1_result.{extension}", dpi=200 if extension == "png" else None,
                       bbox_inches="tight", facecolor="white")
    plt.close(figure)


if __name__ == "__main__":
    main()
