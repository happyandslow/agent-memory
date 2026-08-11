#!/usr/bin/env python3
"""Generate editable SVG + presentation PNG figures for the 2026-08-11 deck."""

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle
import numpy as np


HERE = Path(__file__).resolve().parent
OUT = HERE / "figures"
OUT.mkdir(parents=True, exist_ok=True)

INK = "#18181B"
BODY = "#52525B"
MUTED = "#A1A1AA"
RULE = "#E4E4E7"
ACCENT = "#6D28D9"
BLUE = "#1D4ED8"
GREEN = "#047857"
AMBER = "#B45309"
RED = "#B91C1C"
VIOLET_TINT = "#F2EDFD"
BLUE_TINT = "#E9F0FE"
GREEN_TINT = "#E5F4EE"
CARD = "#F4F4F5"

plt.rcParams.update({
    "font.family": "Arimo",
    "font.size": 14,
    "axes.titlesize": 18,
    "axes.labelsize": 14,
    "xtick.labelsize": 12,
    "ytick.labelsize": 12,
    "text.color": INK,
    "axes.labelcolor": BODY,
    "axes.edgecolor": RULE,
    "xtick.color": BODY,
    "ytick.color": BODY,
})


def save(fig, name):
    fig.savefig(OUT / f"{name}.svg", bbox_inches="tight", facecolor="white")
    fig.savefig(OUT / f"{name}.png", dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def box(ax, xy, w, h, text, fc=CARD, ec=RULE, tc=INK, size=14, lw=1.5, radius=0.02):
    p = FancyBboxPatch(xy, w, h,
                       boxstyle=f"round,pad=0.012,rounding_size={radius}",
                       facecolor=fc, edgecolor=ec, linewidth=lw)
    ax.add_patch(p)
    ax.text(xy[0] + w / 2, xy[1] + h / 2, text, ha="center", va="center",
            color=tc, fontsize=size, weight="bold")
    return p


def arrow(ax, a, b, color=BODY, lw=2.0, style="-|>", rad=0.0):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle=style, mutation_scale=15,
                                color=color, linewidth=lw,
                                connectionstyle=f"arc3,rad={rad}"))


def serving_timeline():
    fig, ax = plt.subplots(figsize=(15.6, 6.7))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    stages = [(0.03, "t0 · Request A served"), (0.35, "t1 · Request B arrives"),
              (0.68, "t2 · Continue + commit")]
    for x, title in stages:
        ax.text(x, 0.94, title, fontsize=17, weight="bold", color=INK)

    # t0
    box(ax, (0.03, 0.62), 0.25, 0.13, "Request A\nprompt + decode", BLUE_TINT, BLUE, BLUE, 15)
    arrow(ax, (0.155, 0.60), (0.155, 0.48), BLUE)
    ax.text(0.03, 0.43, "Resident slot after A", color=BODY, fontsize=13, weight="bold")
    ax.add_patch(Rectangle((0.03, 0.29), 0.15, 0.10, color=GREEN_TINT, ec=GREEN, lw=1.5))
    ax.add_patch(Rectangle((0.18, 0.29), 0.10, 0.10, color=BLUE_TINT, ec=BLUE, lw=1.5))
    ax.text(0.105, 0.34, "shareable prefix", ha="center", va="center", color=GREEN, fontsize=12)
    ax.text(0.23, 0.34, "A history", ha="center", va="center", color=BLUE, fontsize=12)

    # t1
    box(ax, (0.35, 0.68), 0.26, 0.11, "Request B prompt", VIOLET_TINT, ACCENT, ACCENT, 15)
    ax.add_patch(Rectangle((0.35, 0.49), 0.15, 0.10, color=GREEN_TINT, ec=GREEN, lw=1.5))
    ax.add_patch(Rectangle((0.50, 0.49), 0.11, 0.10, color=VIOLET_TINT, ec=ACCENT, lw=1.5))
    ax.text(0.425, 0.54, "matched prefix", ha="center", va="center", color=GREEN, fontsize=12)
    ax.text(0.555, 0.54, "new suffix", ha="center", va="center", color=ACCENT, fontsize=12)
    arrow(ax, (0.28, 0.34), (0.35, 0.54), GREEN, 2.3)
    ax.text(0.315, 0.49, "match", ha="center", color=GREEN, fontsize=12, weight="bold")
    ax.text(0.35, 0.31, "Plan: reuse prefix in place\nforce-decode only the suffix", color=BODY,
            fontsize=14, ha="left", va="center")

    # t2
    ax.text(0.68, 0.80, "time →", color=MUTED, fontsize=13)
    ax.add_patch(Rectangle((0.68, 0.62), 0.13, 0.12, color=GREEN_TINT, ec=GREEN, lw=1.5))
    ax.add_patch(Rectangle((0.81, 0.62), 0.08, 0.12, color=VIOLET_TINT, ec=ACCENT, lw=1.5))
    ax.add_patch(Rectangle((0.89, 0.62), 0.08, 0.12, color=BLUE_TINT, ec=BLUE, lw=1.5))
    ax.text(0.745, 0.68, "reuse", ha="center", va="center", color=GREEN, fontsize=13, weight="bold")
    ax.text(0.85, 0.68, "forced", ha="center", va="center", color=ACCENT, fontsize=12, weight="bold")
    ax.text(0.93, 0.68, "free", ha="center", va="center", color=BLUE, fontsize=12, weight="bold")
    arrow(ax, (0.61, 0.54), (0.68, 0.68), ACCENT, 2.3)
    box(ax, (0.70, 0.30), 0.24, 0.14, "B now owns the slot\nledger + recency commit", CARD, RULE, INK, 14)
    ax.text(0.68, 0.20, "State changes only after the round succeeds", color=BODY, fontsize=13)
    ax.text(0.03, 0.08, "Example: B shares A's resident system prefix; the appliance skips that work, rebuilds only B's suffix, then decodes normally.",
            color=BODY, fontsize=13)
    save(fig, "serving_timeline")


def experiment_a():
    r_partial = np.array([0, 256, 512, 768])
    m1_partial = np.array([222.986, 191.574, 160.156, 141.672])
    m2_partial = np.array([264.269, 232.592, 201.164, 172.098])
    r_exact = np.array([256, 512, 768, 1024])
    m1_exact = np.array([122.662, 124.071, 125.464, 126.957])
    m2_exact = np.array([151.223, 152.035, 152.819, 153.763])
    fig, axes = plt.subplots(1, 2, figsize=(15.6, 6.6), sharey=True)
    for ax, title, partial, exact in zip(
            axes, ["Batch size 1", "Batch size 2"], [m1_partial, m2_partial], [m1_exact, m2_exact]):
        ax.plot(r_partial, partial, marker="o", ms=8, lw=3, color=ACCENT, label="Miss → partial hit")
        ax.plot(r_exact, exact, marker="o", ms=8, lw=3, color=BLUE, label="Exact hit (F=1)")
        ax.fill_between(r_partial, partial - 0.8, partial + 0.8, color=ACCENT, alpha=0.08)
        ax.set_title(title, loc="left", weight="bold", pad=12)
        ax.set_xlabel("Reusable prefix R (tokens)")
        ax.grid(axis="y", color=RULE, linewidth=1)
        ax.spines[["top", "right"]].set_visible(False)
        ax.set_xlim(-30, 1060); ax.set_ylim(105, 285)
        ax.annotate(f"{partial[0]/partial[-1]:.2f}×", (768, partial[-1]), xytext=(680, partial[-1]+24),
                    arrowprops=dict(arrowstyle="->", color=ACCENT), color=ACCENT, weight="bold")
        ax.annotate(f"{partial[0]/exact[0]:.2f}×", (256, exact[0]), xytext=(330, exact[0]-5),
                    arrowprops=dict(arrowstyle="->", color=BLUE), color=BLUE, weight="bold")
    axes[0].set_ylabel("Round TSC time (ms @ 1.1 GHz)")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=2, frameon=False, bbox_to_anchor=(0.5, -0.01))
    fig.suptitle("Longer resident prefixes reduce total round work", x=0.06, ha="left", fontsize=19, weight="bold")
    fig.tight_layout(rect=[0, 0.08, 1, 0.92])
    save(fig, "experiment_a")


def experiment_b():
    labels = ["W2\ndistance 1", "W3\ndistance 2", "W5\ndistance 4", "No reuse"]
    s2 = np.array([171.366, 322.685, 322.678, 322.291])
    s4 = np.array([171.728, 190.633, 322.926, 322.735])
    hits2 = [8, 0, 0, 0]; hits4 = [8, 7, 0, 0]
    x = np.arange(len(labels)); w = 0.34
    fig, ax = plt.subplots(figsize=(15.6, 6.5))
    b1 = ax.bar(x-w/2, s2, w, color=VIOLET_TINT, edgecolor=ACCENT, linewidth=2, label="2 slots")
    b2 = ax.bar(x+w/2, s4, w, color=BLUE_TINT, edgecolor=BLUE, linewidth=2, label="4 slots")
    for bars, hits in [(b1, hits2), (b2, hits4)]:
        for bar, h in zip(bars, hits):
            ax.text(bar.get_x()+bar.get_width()/2, bar.get_height()+8, f"{h}/10 hits",
                    ha="center", va="bottom", fontsize=12, color=BODY, weight="bold")
    ax.annotate("4 slots cross the W3\nworking-set threshold\n1.69× faster",
                xy=(1+w/2, s4[1]), xytext=(1.75, 225),
                arrowprops=dict(arrowstyle="->", color=GREEN, lw=2), color=GREEN,
                fontsize=14, weight="bold", ha="left")
    ax.set_ylabel("10-round TSC time (ms @ 1.1 GHz)")
    ax.set_xticks(x, labels)
    ax.set_ylim(0, 390)
    ax.grid(axis="y", color=RULE, linewidth=1)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, loc="upper left", ncol=2)
    fig.tight_layout()
    save(fig, "experiment_b")


def ragged_execution():
    fig, ax = plt.subplots(figsize=(15.6, 6.7))
    ax.set_xlim(0, 1050); ax.set_ylim(-0.3, 4.5); ax.axis("off")
    ax.text(0, 4.15, "Current: one common start for the whole batch", fontsize=18, weight="bold")
    lanes = [("Lane A · long system prefix", 768, 3.25), ("Lane B · short prefix", 256, 2.55)]
    for label, hit, y in lanes:
        ax.text(0, y+0.18, label, ha="left", va="center", fontsize=14, weight="bold")
        ax.add_patch(Rectangle((255, y), hit-255, 0.35, color=GREEN_TINT, ec=GREEN, lw=1.3))
        ax.add_patch(Rectangle((hit, y), 1024-hit, 0.35, color=VIOLET_TINT, ec=ACCENT, lw=1.3))
    ax.axvline(256, ymin=0.49, ymax=0.78, color=RED, lw=2, ls="--")
    ax.text(270, 3.78, "common start = 256", color=RED, fontsize=13, weight="bold")
    ax.text(430, 3.42, "512 tokens unnecessarily recomputed for Lane A", color=RED, fontsize=13)
    ax.text(0, 1.65, "Needed: per-lane cursors inside the same round", fontsize=18, weight="bold")
    lanes2 = [("Lane A", 768, 0.85), ("Lane B", 256, 0.15)]
    for label, hit, y in lanes2:
        ax.text(0, y+0.18, label, ha="left", va="center", fontsize=14, weight="bold")
        ax.add_patch(Rectangle((0, y), hit, 0.35, color=GREEN_TINT, ec=GREEN, lw=1.3))
        ax.add_patch(Rectangle((hit, y), 1024-hit, 0.35, color=BLUE_TINT, ec=BLUE, lw=1.3))
        ax.text(hit+12, y+0.18, f"start {hit}", va="center", color=BLUE, fontsize=12, weight="bold")
    for xx in [0, 256, 512, 768, 1024]:
        ax.text(xx, -0.17, str(xx), ha="center", va="top", color=MUTED, fontsize=11)
    ax.text(790, 1.15, "Different lanes compute\ndifferent token positions", color=BODY, fontsize=14,
            bbox=dict(boxstyle="round,pad=.45", fc=CARD, ec=RULE))
    save(fig, "ragged_execution")


def mixed_layout():
    fig, ax = plt.subplots(figsize=(15.6, 6.8))
    ax.set_xlim(-1.2, 10.6); ax.set_ylim(-0.9, 8.9); ax.axis("off")
    ax.text(-1.1, 8.45, "P = 8 example: host seed is contiguous; later decode appends round-robin", fontsize=18, weight="bold")
    ax.text(-1.05, 7.85, "PE row", color=BODY, fontsize=13, weight="bold")
    for r in range(8):
        y = 7-r
        ax.text(-0.35, y+0.25, f"{r}", ha="center", va="center", fontsize=13, weight="bold")
        seed = [2*r, 2*r+1]
        for j, token in enumerate(seed):
            ax.add_patch(Rectangle((j*1.3, y), 1.08, 0.5, fc=GREEN_TINT, ec=GREEN, lw=1.3))
            ax.text(j*1.3+0.54, y+0.25, f"seed {token}", ha="center", va="center", color=GREEN, fontsize=11)
        if r < 4:
            ax.add_patch(Rectangle((2.6, y), 1.08, 0.5, fc=BLUE_TINT, ec=BLUE, lw=1.3))
            ax.text(3.14, y+0.25, f"dec {16+r}", ha="center", va="center", color=BLUE, fontsize=11)
        count = 3 if r < 4 else 2
        ax.text(4.15, y+0.25, f"local depth {count}", va="center", color=BODY, fontsize=12)
    ax.axvline(2.48, ymin=0.05, ymax=0.86, color=RED, lw=2, ls="--")
    ax.text(5.6, 6.7, "A 20-token logical prefix\nlands at different local depths", fontsize=16,
            weight="bold", color=INK)
    box(ax, (5.6, 4.7), 4.2, 1.25,
        "Current mitigation\nround down to one safe boundary\n(drop < one P-token block)",
        VIOLET_TINT, ACCENT, ACCENT, 14)
    box(ax, (5.6, 2.7), 4.2, 1.25,
        "Full solution\nper-row reuse cursors + addressing\nmay move control on-chip",
        BLUE_TINT, BLUE, BLUE, 14)
    ax.text(5.6, 1.55, "Priority: lower for now", color=AMBER, fontsize=15, weight="bold")
    ax.text(5.6, 1.05, "Block edge is modest; truncation cost is bounded, but must be measured.", color=BODY, fontsize=13)
    save(fig, "mixed_layout")


def m3_placement():
    fig, ax = plt.subplots(figsize=(15.6, 6.8))
    ax.set_xlim(0, 16); ax.set_ylim(0, 8); ax.axis("off")
    ax.text(0.2, 7.6, "Direction: placement-agnostic policy, statically realizable movement", fontsize=18, weight="bold")
    # wafer / blocks
    ax.add_patch(FancyBboxPatch((0.4, 0.6), 7.3, 6.3, boxstyle="round,pad=.04,rounding_size=.12",
                                fc="white", ec=INK, lw=2))
    for row in range(4):
        for col in range(2):
            x=0.75+col*2.55; y=5.55-row*1.25
            ax.add_patch(Rectangle((x,y),2.15,0.9,fc=VIOLET_TINT,ec=ACCENT,lw=1.2))
            ax.text(x+1.075,y+0.45,f"compute B{row*2+col}",ha="center",va="center",fontsize=11,color=ACCENT,weight="bold")
    ax.add_patch(Rectangle((6.1,0.9),1.15,5.8,fc=GREEN_TINT,ec=GREEN,lw=1.5))
    ax.text(6.68,3.8,"idle\neast\nstrip",ha="center",va="center",color=GREEN,fontsize=13,weight="bold")
    ax.add_patch(Rectangle((0.75,0.9),5.05,0.65,fc=GREEN_TINT,ec=GREEN,lw=1.5))
    ax.text(3.27,1.22,"idle south strip",ha="center",va="center",color=GREEN,fontsize=12,weight="bold")
    for pt in [(5.45,6.25),(5.7,4.2),(0.6,3.0)]:
        ax.scatter(*pt,s=120,color=BLUE,marker="s")
    ax.text(0.75,0.25,"Candidate storage can live in any usable region — but routes are not keyed at runtime.",color=BODY,fontsize=12)
    arrow(ax,(7.7,3.8),(8.7,3.8),ACCENT,2.4)
    # profile contract
    box(ax,(8.8,5.4),6.6,1.25,"Storage region advertises\ncapacity + static route family",VIOLET_TINT,ACCENT,ACCENT,15)
    box(ax,(8.8,3.65),6.6,1.25,"Measured cost profile\npark(bytes, distance, rows)\nreload(bytes, distance, rows)",BLUE_TINT,BLUE,BLUE,15)
    box(ax,(8.8,1.9),6.6,1.25,"Planner chooses placement\nusing lifetime + expected reuse",GREEN_TINT,GREEN,GREEN,15)
    ax.text(8.8,0.75,"First prototype: one fixed edge strip. Long-term API: a catalog of precompiled/static placements.",color=BODY,fontsize=13)
    save(fig, "m3_placement")


def edge_strip():
    fig, ax = plt.subplots(figsize=(15.6, 6.8))
    ax.set_xlim(0, 15.5); ax.set_ylim(0, 8); ax.axis("off")
    ax.text(0.2,7.6,"Concrete probe: attach horizontal storage rows under each PE block",fontsize=18,weight="bold")
    # block grid schematic
    x0,y0,w,h=0.5,1.5,7.0,5.3
    ax.add_patch(Rectangle((x0,y0),w,h,fc=VIOLET_TINT,ec=ACCENT,lw=2))
    for i in range(1,8):
        ax.plot([x0+i*w/8]*2,[y0,y0+h],color="white",lw=1)
        ax.plot([x0,x0+w],[y0+i*h/8]*2,color="white",lw=1)
    ax.text(x0+w/2,y0+h/2,"P × P compute block\n(P = 256)",ha="center",va="center",fontsize=18,color=ACCENT,weight="bold")
    rows=3
    for r in range(rows):
        yy=y0-0.28*(r+1)
        ax.add_patch(Rectangle((x0,yy),w,0.22,fc=GREEN_TINT,ec=GREEN,lw=1))
    ax.text(x0+w/2,0.35,"k horizontal storage rows",ha="center",va="center",color=GREEN,fontsize=14,weight="bold")
    for i in [0.7,2.2,3.7,5.2,6.7]:
        arrow(ax,(i,2.0),(i,1.05),GREEN,1.6)
    # capacity cards
    box(ax,(8.4,5.55),6.4,1.05,"1 row × 256 PEs × 42 KiB\n≈ 10.5 MiB per block",GREEN_TINT,GREEN,GREEN,15)
    box(ax,(8.4,3.85),6.4,1.05,"Full-model KV density per block\n≈ 16 KiB / token (8 blocks)",BLUE_TINT,BLUE,BLUE,15)
    box(ax,(8.4,2.15),6.4,1.05,"One row stores ≈ 672 tokens\n≈ 13 rows for one 8K request",VIOLET_TINT,ACCENT,ACCENT,15)
    ax.text(8.4,1.15,"All numbers are analytical and use the nominal 42 KiB storage payload; E2 must compile-probe the real cap.",color=BODY,fontsize=12)
    ax.text(8.4,0.65,"Open: can k rows move concurrently without stealing live colors/queues from decode?",color=AMBER,fontsize=13,weight="bold")
    save(fig,"edge_strip")


def eviction_model():
    # Real full-scale E10 resume anchors. This is one boundary slice, not a
    # universal policy threshold: full-target reload also depends on S/L_new.
    L=np.array([512,1024,2048,4096,8192])
    force=np.array([37.9,76.9,158.3,333.5,735.1])
    host=np.array([46.236,56.141,85.684,169.891,338.266])
    # M3 edge-strip band remains analytical until E1 measures it on device.
    best=np.array([2.3,2.4,2.4,2.5,2.7])
    serialized=np.array([2.4,4.8,9.0,17.5,35.0])
    fig,ax=plt.subplots(figsize=(15.6,6.5))
    ax.plot(L,force,marker="o",lw=3,color=ACCENT,label="Measured recompute / force-decode")
    ax.plot(L,host,marker="o",lw=3,color=BLUE,label="Measured host reload (resume only)")
    ax.fill_between(L,best,serialized,color=GREEN,alpha=.18,label="Analytical edge-strip park+reload")
    ax.plot(L,best,ls="--",lw=2,color=GREEN)
    ax.plot(L,serialized,ls="--",lw=2,color=GREEN)
    ax.set_xscale("log",base=2)
    ax.set_yscale("log")
    ax.set_xticks(L,labels=[f"{x:,}" for x in L])
    ax.set_xlabel("Resident history H (tokens)")
    ax.set_ylabel("Resume / rebuild cost (ms, log scale)")
    ax.grid(True,which="both",color=RULE,lw=1)
    ax.spines[["top","right"]].set_visible(False)
    ax.legend(frameon=False,loc="upper left")
    ax.axvline(700,color=AMBER,ls=":",lw=2)
    ax.text(725,30,"≈700-token crossing\n(this E10 slice)",color=AMBER,fontsize=13,weight="bold")
    ax.text(2800,4.3,"analytic band only\n≈2.3 ms if rows move in parallel\nup to k× if stripes serialize",color=GREEN,fontsize=13,weight="bold")
    ax.text(.99,.04,"Real Qwen3-1.7B · one WSE-3 · bsz 1 · 0.85 GHz TSC",
            transform=ax.transAxes,ha="right",color=BODY,fontsize=11)
    fig.tight_layout()
    save(fig,"eviction_model")


if __name__ == "__main__":
    serving_timeline()
    experiment_a()
    experiment_b()
    ragged_execution()
    mixed_layout()
    m3_placement()
    edge_strip()
    eviction_model()
