#!/usr/bin/env python3
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyBboxPatch


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "figures"
OUT.mkdir(exist_ok=True)

VIOLET = "#6D28D9"
BLUE = "#1D4ED8"
GREEN = "#047857"
INK = "#18181B"
BODY = "#52525B"
MUTED = "#A1A1AA"
RULE = "#E4E4E7"


def style_ax(ax):
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color(RULE)
    ax.grid(axis="y", color=RULE, linewidth=0.9)
    ax.set_axisbelow(True)
    ax.tick_params(colors=BODY, labelsize=12)


def save(fig, name):
    fig.savefig(OUT / name, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)


plt.rcParams.update({
    "font.family": "Arial",
    "font.size": 13,
    "axes.labelcolor": BODY,
    "text.color": INK,
    # Keep labels as editable text in the companion SVG exports.
    "svg.fonttype": "none",
})


# Logical on-chip topology of the pdSeparate implementation used by the study.
# The central 2x4 block grid preserves the measured configuration's geometry;
# the narrow surrounding regions show the actual host/HT/KV roles without
# attempting to draw all 512x1024 worker PEs.
fig, ax = plt.subplots(figsize=(14.2, 7.0))
ax.set_xlim(0, 14.2)
ax.set_ylim(0, 7.0)
ax.axis("off")

PREFILL = "#EA580C"
PREFILL_LIGHT = "#FFF1E7"
DECODE = "#2563EB"
DECODE_LIGHT = "#EAF1FF"
IO_FILL = "#F4F4F5"
KV = "#059669"
KV_LIGHT = "#E7F7F1"
HOST_FILL = "#FEFCE8"


def topo_box(x, y, w, h, label, edge, fill, size=9.5, weight="bold", z=2):
    patch = FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.04,rounding_size=0.08",
        linewidth=1.35, edgecolor=edge, facecolor=fill, zorder=z,
    )
    ax.add_patch(patch)
    ax.text(x + w / 2, y + h / 2, label, ha="center", va="center",
            fontsize=size, color=INK, weight=weight, zorder=z + 1)


def topo_arrow(x1, y1, x2, y2, color, width=1.8, dashed=False, z=4):
    ax.annotate(
        "", xy=(x2, y2), xytext=(x1, y1),
        arrowprops=dict(arrowstyle="-|>", color=color, linewidth=width,
                        linestyle="--" if dashed else "-", shrinkA=0, shrinkB=0),
        zorder=z,
    )


def draw_worker_grid(x0, y0, accent, fill, prefix):
    """Draw the 2 columns x 4 rows of 256x256-PE logical blocks."""
    bw, bh, gx, gy = 1.22, 0.62, 0.18, 0.18
    centers = []
    block = 0
    # Serpentine pipeline: bottom row W->E, then alternate by row.
    for row in range(4):
        cols = range(2) if row % 2 == 0 else range(1, -1, -1)
        for col in cols:
            x = x0 + col * (bw + gx)
            y = y0 + row * (bh + gy)
            topo_box(x, y, bw, bh, f"B{block}\n256×256 PEs", accent, fill, 8.3)
            centers.append((x + bw / 2, y + bh / 2))
            block += 1
    for (xa, ya), (xb, yb) in zip(centers[:-1], centers[1:]):
        if abs(ya - yb) < 0.05:
            start = (xa + (0.61 if xb > xa else -0.61), ya)
            end = (xb - (0.61 if xb > xa else -0.61), yb)
        else:
            start = (xa, ya + 0.31)
            end = (xb, yb - 0.31)
        topo_arrow(*start, *end, accent, width=1.45)
    ax.text(x0 + 1.31, y0 + 3.50, f"{prefix} COMPUTE FABRIC",
            ha="center", fontsize=9.5, color=accent, weight="bold")


# Host memories make the PD-separated boundary explicit.
topo_box(1.47, 6.12, 4.35, 0.60, "PREFILL HOST DRAM", "#CA8A04", HOST_FILL, 11)
topo_box(8.38, 6.12, 4.35, 0.60, "DECODE HOST DRAM", "#CA8A04", HOST_FILL, 11)
topo_arrow(5.82, 6.42, 8.38, 6.42, KV, dashed=True)
ax.text(7.10, 6.66, "host-mediated KV bridge", ha="center", fontsize=9.2,
        color=KV, weight="bold")

# Card outlines.
for x, title, accent in [(0.22, "PREFILL WSE-3", PREFILL), (7.32, "DECODE WSE-3", DECODE)]:
    card = FancyBboxPatch((x, 0.72), 6.66, 5.08,
                          boxstyle="round,pad=0.05,rounding_size=0.10",
                          linewidth=2.0, edgecolor=accent, facecolor="white", zorder=0)
    ax.add_patch(card)
    ax.text(x + 0.25, 5.52, title, fontsize=12, color=accent, weight="bold")

# Prefill: host token input -> HT head -> 2x4 blocks -> HT tail/logits.
topo_box(0.50, 4.30, 1.18, 0.68, "demux\n(token IDs)", BODY, IO_FILL, 8.6)
topo_box(0.50, 3.40, 1.18, 0.68, "HT head\nembedding", BODY, IO_FILL, 8.6)
draw_worker_grid(2.00, 1.47, PREFILL, PREFILL_LIGHT, "PREFILL")
topo_box(4.95, 3.20, 1.15, 0.75, "HT tail\nLM head", BODY, IO_FILL, 8.7)
topo_box(4.95, 2.17, 1.15, 0.62, "logits mux", BODY, IO_FILL, 8.5)
topo_box(6.27, 1.47, 0.38, 3.02, "", KV, KV_LIGHT, 8.1)
ax.text(6.46, 2.98, "KV mux", ha="center", va="center", rotation=90,
        fontsize=8.5, color=INK, weight="bold")
ax.text(3.31, 5.15, "8 blocks · 28 layers: 2 · 4 · 4 · 4 · 4 · 4 · 4 · 2",
        ha="center", fontsize=8.1, color=BODY)

topo_arrow(1.09, 6.12, 1.09, 4.98, BODY)
topo_arrow(1.09, 4.30, 1.09, 4.08, BODY)
topo_arrow(1.68, 3.74, 2.00, 3.74, PREFILL)
topo_arrow(4.62, 4.18, 4.95, 3.58, PREFILL)
topo_arrow(5.53, 3.20, 5.53, 2.79, BODY)
topo_arrow(5.53, 2.17, 5.53, 1.00, BODY)
ax.text(5.34, 0.84, "tokens / logits → host", ha="center", fontsize=8.3, color=BODY)

# KV leaves every prefill row to the east, then the vertical mux drains north.
for yy in [1.78, 2.58, 3.38, 4.18]:
    topo_arrow(4.62, yy, 6.27, yy, KV, width=1.6)
topo_arrow(6.46, 4.49, 6.46, 6.12, KV, width=2.1)
ax.text(5.43, 4.73, "switch-gather EAST", ha="center", fontsize=8.2,
        color=KV, weight="bold")
ax.text(6.18, 5.27, "drain\nNORTH", ha="right", fontsize=8.0, color=KV, weight="bold")

# Decode: host KV stream -> adaptor -> horizontal demux -> north into the fabric.
topo_box(7.58, 4.30, 1.18, 0.68, "demux\n(token IDs)", BODY, IO_FILL, 8.6)
topo_box(7.58, 3.40, 1.18, 0.68, "HT head\nembedding", BODY, IO_FILL, 8.6)
draw_worker_grid(9.08, 1.47, DECODE, DECODE_LIGHT, "DECODE")
topo_box(12.03, 3.20, 1.15, 0.75, "HT tail\nTop-K/sample", BODY, IO_FILL, 8.4)
topo_box(12.03, 2.17, 1.15, 0.62, "output mux", BODY, IO_FILL, 8.5)
topo_box(8.98, 0.88, 0.72, 0.43, "adaptor", KV, KV_LIGHT, 7.7)
topo_box(9.82, 0.88, 1.88, 0.43, "KV demux (Pw×1)", KV, KV_LIGHT, 7.7)
ax.text(10.39, 5.15, "8 blocks · 28 layers: 2 · 4 · 4 · 4 · 4 · 4 · 4 · 2",
        ha="center", fontsize=8.1, color=BODY)

topo_arrow(8.17, 6.12, 8.17, 4.98, BODY)
topo_arrow(8.17, 4.30, 8.17, 4.08, BODY)
topo_arrow(8.76, 3.74, 9.08, 3.74, DECODE)
topo_arrow(11.70, 4.18, 12.03, 3.58, DECODE)
topo_arrow(12.61, 3.20, 12.61, 2.79, BODY)
topo_arrow(12.61, 2.17, 12.61, 1.00, BODY)
ax.text(12.42, 0.84, "tokens / logits → host", ha="center", fontsize=8.3, color=BODY)

topo_arrow(8.72, 6.12, 8.72, 1.09, KV, width=2.0)
topo_arrow(8.72, 1.09, 8.98, 1.09, KV, width=2.0)
topo_arrow(9.70, 1.09, 9.82, 1.09, KV, width=2.0)
for xx in [9.39, 10.79]:
    topo_arrow(xx, 1.31, xx, 1.47, KV, width=1.7)
ax.text(8.52, 2.05, "host KV\nstream", ha="right", fontsize=8.2,
        color=KV, weight="bold")

# Compact, fully labelled legend.
legend_y = 0.22
legend_items = [
    (0.45, PREFILL_LIGHT, PREFILL, "prefill compute"),
    (2.45, DECODE_LIGHT, DECODE, "decode compute"),
    (4.45, IO_FILL, BODY, "HT / token I/O"),
    (6.45, KV_LIGHT, KV, "KV routing region"),
]
for x, fill, edge, label in legend_items:
    topo_box(x, legend_y - 0.02, 0.42, 0.22, "", edge, fill, 1)
    ax.text(x + 0.52, legend_y + 0.09, label, va="center", fontsize=8.3, color=BODY)
topo_arrow(9.00, legend_y + 0.09, 9.55, legend_y + 0.09, BODY, width=1.4)
ax.text(9.65, legend_y + 0.09, "on-wafer", va="center", fontsize=8.3, color=BODY)
topo_arrow(11.05, legend_y + 0.09, 11.60, legend_y + 0.09, KV, width=1.4, dashed=True)
ax.text(11.70, legend_y + 0.09, "off-wafer / host", va="center", fontsize=8.3, color=BODY)

save(fig, "pdseparate_topology.png")


# Three request paths on the same simplified PD-separated topology. One PE box
# represents the full 2x4 compute fabric shown on the preceding slide.
fig, ax = plt.subplots(figsize=(14.2, 7.0))
ax.set_xlim(0, 14.2)
ax.set_ylim(0, 7.0)
ax.axis("off")

cols = {"pf_host": 2.65, "pf_pe": 5.25, "dc_host": 8.05, "dc_pe": 10.65, "result": 13.15}
box_w, box_h = 1.82, 0.82


def box(x, y, text, edge, fill, muted=False, pe=False):
    w = 1.52 if pe else box_w
    patch = FancyBboxPatch((x-w/2, y-box_h/2), w, box_h,
                           boxstyle="round,pad=0.06,rounding_size=0.12",
                           linewidth=1.7, edgecolor=edge, facecolor=fill, zorder=2)
    ax.add_patch(patch)
    ax.text(x, y, text, ha="center", va="center", fontsize=10.3,
            color=MUTED if muted else INK, weight="bold" if not muted else "normal", zorder=3)


def edge_x(x, pe=False):
    return x + (0.76 if pe else box_w/2)


def arrow_between(x1, x2, y, label, color, dashed=False, src_pe=False, dst_pe=False, lift=0.52):
    start = x1 + (0.76 if src_pe else box_w/2)
    end = x2 - (0.76 if dst_pe else box_w/2)
    ax.annotate("", xy=(end, y), xytext=(start, y),
                arrowprops=dict(arrowstyle="-|>", color=color, linewidth=2.1,
                                linestyle="--" if dashed else "-"), zorder=4)
    ax.text((start+end)/2, y+lift, label, ha="center", va="bottom",
            fontsize=8.8, color=color, weight="bold", zorder=5)


# Shared component columns connect directly to the detailed topology on slide 2.
ax.text(3.95, 6.62, "PREFILL CARD", ha="center", fontsize=12.5, color=PREFILL, weight="bold")
ax.text(9.35, 6.62, "DECODE CARD", ha="center", fontsize=12.5, color=DECODE, weight="bold")
for x, label in [(cols["pf_host"], "HOST DRAM"), (cols["pf_pe"], "1 representative PE"),
                 (cols["dc_host"], "HOST DRAM"), (cols["dc_pe"], "1 representative PE"),
                 (cols["result"], "RESULT")]:
    ax.text(x, 6.25, label, ha="center", fontsize=8.8, color=MUTED, weight="bold")
ax.text(7.10, 5.91, "One PE stands for the full kernel fabric; arrows show request/state movement",
        ha="center", fontsize=9.2, color=BODY)

rows = [("A", "RECOMPUTE", 5.05, VIOLET), ("B", "RELOAD", 3.28, BLUE), ("C", "PREFILL", 1.51, GREEN)]
for lane, name, y, color in rows:
    ax.text(0.18, y+0.02, lane, fontsize=25, color=color, weight="bold", va="center")
    ax.text(0.62, y+0.02, name, fontsize=10.8, color=BODY, weight="bold", va="center")
    ax.plot([0.18, 13.98], [y-0.77, y-0.77], color=RULE, linewidth=1.0, zorder=0)
    for x0 in [1.62, 7.02]:
        card = FancyBboxPatch((x0, y-0.60), 5.02, 1.20,
                              boxstyle="round,pad=0.03,rounding_size=0.08",
                              linewidth=0.9, edgecolor=RULE, facecolor="#FCFCFD", zorder=0)
        ax.add_patch(card)

# A: only the decode card runs; all history and new IDs are replayed.
y = 5.05
box(cols["pf_host"], y, "not used", RULE, "#FAFAFA", muted=True)
box(cols["pf_pe"], y, "PE\nidle", RULE, "#FAFAFA", muted=True, pe=True)
box(cols["dc_host"], y, "IDs\nLhist + Lnew", VIOLET, "#F2EDFD")
box(cols["dc_pe"], y, "PE\nforce-decode all", VIOLET, "#F2EDFD", pe=True)
box(cols["result"], y, "KV ready", VIOLET, "white")
arrow_between(cols["dc_host"], cols["dc_pe"], y, "token IDs", VIOLET, dst_pe=True)
arrow_between(cols["dc_pe"], cols["result"], y, "rebuilt KV", VIOLET, src_pe=True)

# B: persisted history KV and new IDs enter decode; only the delta is computed.
y = 3.28
box(cols["pf_host"], y, "not used", RULE, "#FAFAFA", muted=True)
box(cols["pf_pe"], y, "PE\nidle", RULE, "#FAFAFA", muted=True, pe=True)
box(cols["dc_host"], y, "KV(Lhist)\n+ IDs(Lnew)", BLUE, "#E9F0FE")
box(cols["dc_pe"], y, "PE\nload + force delta", BLUE, "#E9F0FE", pe=True)
box(cols["result"], y, "KV ready", BLUE, "white")
arrow_between(cols["dc_host"], cols["dc_pe"], y, "KV ingress + IDs", BLUE, dst_pe=True)
arrow_between(cols["dc_pe"], cols["result"], y, "completed KV", BLUE, src_pe=True)

# C: new IDs enter prefill, the PE extends resident history, and completed KV
# returns through the two host memories before entering decode.
y = 1.51
box(cols["pf_host"], y, "Lnew IDs in\ncompleted KV out", GREEN, "#E5F4EE")
box(cols["pf_pe"], y, "PE\nLhist resident", GREEN, "#E5F4EE", pe=True)
box(cols["dc_host"], y, "completed\nKV state", GREEN, "#E5F4EE")
box(cols["dc_pe"], y, "PE\nKV ingress", GREEN, "#E5F4EE", pe=True)
box(cols["result"], y, "KV ready", GREEN, "white")
# Two curved arrows make the request-in / KV-out directions unambiguous.
ax.annotate("", xy=(cols["pf_pe"]-0.76, y+0.18), xytext=(cols["pf_host"]+box_w/2, y+0.18),
            arrowprops=dict(arrowstyle="-|>", color=GREEN, linewidth=2.0,
                            connectionstyle="arc3,rad=-0.12"), zorder=4)
ax.text(3.95, y+0.43, "Lnew IDs", ha="center", fontsize=8.7, color=GREEN, weight="bold")
ax.annotate("", xy=(cols["pf_host"]+box_w/2, y-0.18), xytext=(cols["pf_pe"]-0.76, y-0.18),
            arrowprops=dict(arrowstyle="-|>", color=GREEN, linewidth=2.0,
                            connectionstyle="arc3,rad=-0.12"), zorder=4)
ax.text(3.95, y-0.53, "KV egress", ha="center", fontsize=8.7, color=GREEN, weight="bold")
ax.annotate("", xy=(cols["dc_host"]-box_w/2, y+0.20),
            xytext=(cols["pf_host"]+box_w/2, y+0.20),
            arrowprops=dict(arrowstyle="-|>", color=GREEN, linewidth=2.0,
                            linestyle="--", connectionstyle="arc3,rad=-0.22"), zorder=4)
ax.text(6.42, y+0.67, "host ↔ host assumed 0", ha="center", fontsize=8.7,
        color=GREEN, weight="bold")
arrow_between(cols["dc_host"], cols["dc_pe"], y, "KV ingress", GREEN, dst_pe=True)
arrow_between(cols["dc_pe"], cols["result"], y, "state loaded", GREEN, src_pe=True)

ax.text(7.1, 0.18, "Solid = card-local movement   ·   Dashed = off-card host bridge   ·   Decode→host eviction excluded",
        ha="center", fontsize=9.1, color=MUTED)
# Companion vector source: text remains text and all boxes/arrows remain SVG
# elements. The deck itself uses PNG for portable rendering.
fig.savefig(OUT / "three_resume_lanes.svg", bbox_inches="tight", facecolor="white")
save(fig, "three_resume_lanes.png")


def equation_card(ax, x, y, w, h, title, lines, edge, fill):
    patch = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.08,rounding_size=0.12",
                           linewidth=1.5, edgecolor=edge, facecolor=fill)
    ax.add_patch(patch)
    ax.text(x+0.28, y+h-0.38, title, fontsize=13, color=edge, weight="bold", va="top")
    for ypos, line, size in lines:
        ax.text(x+0.28, y+ypos, line, fontsize=size, color=INK, va="center")


# Lane A equation sheet. Render equations into an image so PowerPoint cannot flatten subscripts/sums.
fig, ax = plt.subplots(figsize=(14.2, 6.7))
ax.set_xlim(0, 14.2)
ax.set_ylim(0, 7.0)
ax.axis("off")
ax.text(0.35, 6.45,
        r"$D(P,F)=D(P,256)+\sum_{q=P+256}^{P+F-1} II(q),\qquad F\geq256$",
        fontsize=25, color=INK, va="center")
ax.text(0.35, 5.55,
        r"$D(P,F)=D(P,256)+(F-256)a+\frac{b(F-256)(2P+F+255)}{2}$",
        fontsize=21, color=VIOLET, va="center")
ax.text(0.38, 4.95, "Equivalent closed form for the same discrete sum", fontsize=11.5, color=MUTED)

equation_card(ax, 0.35, 0.75, 4.1, 3.65, "STEADY INTERVAL",
              [(2.45, r"$II(q)=a+bq$", 22),
               (1.55, r"$a=71.745198\ \mu s$", 17),
               (0.78, r"$b=0.004093307\ \mu s/position$", 15)],
              VIOLET, "#F2EDFD")
equation_card(ax, 4.85, 0.75, 5.55, 3.65, "PREFIX-SPECIFIC STARTUP ANCHOR",
              [(2.35, r"$D(P,256)=d_k+\frac{P-p_k}{p_{k+1}-p_k}(d_{k+1}-d_k)$", 16),
               (1.37, r"$P\in[p_k,p_{k+1}]$", 17),
               (0.62, r"$p_k\in\{256,1024,4096,8192\}$", 15)],
              BLUE, "#E9F0FE")
equation_card(ax, 10.8, 0.75, 3.05, 3.65, "MODEL SCOPE",
              [(2.35, "Anchor includes readiness", 13),
               (1.55, "F=1 is not a universal", 13),
               (1.12, "offset to subtract", 13),
               (0.45, "E14: n=1", 13)],
              GREEN, "#E5F4EE")
save(fig, "lane_a_equations.png")


# Lane B equation sheet under the current full-target-KV reload contract.
fig, ax = plt.subplots(figsize=(14.2, 6.7))
ax.set_xlim(0, 14.2)
ax.set_ylim(0, 7.0)
ax.axis("off")
ax.text(0.35, 6.35,
        r"$B_{full}(S,H,L_{new})=I(P_{target})$",
        fontsize=25, color=BLUE, va="center")
ax.text(0.35, 5.40,
        r"$P_{target}=S+H+L_{new}$",
        fontsize=23, color=GREEN, va="center")
ax.text(9.35, 6.35,
        r"$A(S,H,L_{new})=D(S,H+L_{new})$",
        fontsize=17, color=VIOLET, va="center")
ax.text(9.38, 5.88, "Both lanes stop when target KV is ready", fontsize=10.5, color=MUTED)

equation_card(ax, 0.35, 0.75, 6.1, 3.85, "INGRESS MODEL",
              [(2.55, r"$I(h)=t_k+\frac{t_{k+1}-t_k}{h_{k+1}-h_k}(h-h_k)$", 18),
               (1.62, r"$h\in[h_k,h_{k+1}]$", 16),
               (0.72, r"$h_k\in\{256,512,1024,2048,4096,8192\}$", 14)],
              BLUE, "#E9F0FE")
equation_card(ax, 6.85, 0.75, 3.15, 3.85, "COMMON NEXT TOKEN",
              [(2.40, r"$G(P_{target})$", 19),
               (1.43, "Same free-decode step", 12.5),
               (0.96, "after either lane", 12.5),
               (0.35, "excluded from comparison", 12.5)],
              VIOLET, "#F2EDFD")
equation_card(ax, 10.4, 0.75, 3.45, 3.85, "VARIABLES",
              [(2.55, r"$S$: starting prefix", 14),
               (1.80, r"$H$: history to recover", 14),
               (1.05, r"$L_{new}$: new context", 14),
               (0.32, r"$I$: full-KV ingress", 14)],
              GREEN, "#E5F4EE")
save(fig, "lane_b_equations.png")


# E5: all six raw ingress observations.
prefix = np.array([256, 512, 1024, 2048, 4096, 8192])
payload_mb = np.array([37.6, 71.3, 138.4, 272.9, 541.2, 1078.0])
ingress_ms = np.array([46.150, 46.236, 56.141, 85.684, 169.891, 338.266])
fig, ax = plt.subplots(figsize=(12.8, 5.8))
ax.plot(payload_mb, ingress_ms, color=VIOLET, marker="o", linewidth=2.8, markersize=8)
label_offsets = [(-12, 12), (14, 26), (20, 5), (0, 10), (0, 10), (0, 10)]
for x, y, p, offset in zip(payload_mb, ingress_ms, prefix, label_offsets):
    ax.annotate(f"P={p:,}\n{y:.1f} ms", (x, y), xytext=offset,
                textcoords="offset points", ha="center", fontsize=10.5, color=BODY)
ax.set_xlabel("Total KV payload across four ingress bands (MB)")
ax.set_ylabel("Device-TSC ingress span (ms)")
ax.set_title("All six E5 decode-ingress observations", loc="left", fontsize=18, weight="bold")
style_ax(ax)
save(fig, "e5_ingress_raw.png")


# Lane B reload model: the crossing calculation uses interpolation of measured E5 anchors.
fig, ax = plt.subplots(figsize=(12.8, 5.8))
h_dense = np.linspace(256, 8192, 1200)
i_dense = np.interp(h_dense, prefix, ingress_ms)
ax.axvspan(256, 512, color="#F2EDFD", alpha=0.65)
ax.axvspan(512, 2048, color="#E9F0FE", alpha=0.55)
ax.axvspan(2048, 8192, color="#E5F4EE", alpha=0.55)
ax.plot(h_dense, i_dense, color=BLUE, linewidth=2.8, label="I(H): piecewise interpolation")
ax.scatter(prefix, ingress_ms, s=65, color=INK, zorder=3, label="E5 measured anchors")
ax.text(350, 250, "FLOOR\n~46 ms", ha="center", va="center", fontsize=13, color=VIOLET, weight="bold")
ax.text(1050, 310, "KNEE", ha="center", va="center", fontsize=13, color=BLUE, weight="bold")
ax.text(4300, 310, "BYTE-DOMINATED\n~3.186 GB/s", ha="center", va="center", fontsize=13, color=GREEN, weight="bold")
ax.set_xscale("log", base=2)
ax.set_xticks(prefix, [f"{p:,}" for p in prefix])
ax.set_xlabel("Reloaded history H (tokens)")
ax.set_ylabel("KV ingress model I(H) (ms)")
ax.set_title("Reload cost model used by the boundary calculation", loc="left", fontsize=18, weight="bold")
ax.legend(frameon=False, fontsize=11, loc="center left")
style_ax(ax)
save(fig, "lane_b_reload_model.png")


# E14: all 24 raw force-decode spans.
timing_path = Path("/home/lexu/we-m2-prefix-fd-sweep/models/qwen3_1p7b-e2e-pdSeparate/evidence/e14_prefix_fd_sweep_run1/timing.json")
grid_path = Path("/home/lexu/we-m2-prefix-fd-sweep/models/qwen3_1p7b-e2e-pdSeparate/request_config/e14_prefix_fd_sweep/e14_grid/grid.json")
timing = json.loads(timing_path.read_text())
grid = json.loads(grid_path.read_text())
rounds = timing["decode_device"]["tsc"]["per_round"]
records = []
for meta, row in zip(grid["rounds"], rounds):
    records.append((meta["prefix_tokens"], meta["forced_decode_len"], row["fd_span_us"] / 1000.0))

fig, ax = plt.subplots(figsize=(12.8, 5.8))
colors = [VIOLET, BLUE, GREEN, INK]
for color, p in zip(colors, grid["prefixes"]):
    rs = [(f, ms) for pp, f, ms in records if pp == p]
    ax.plot([x for x, _ in rs], [y for _, y in rs], marker="o", linewidth=2.5,
            markersize=7, color=color, label=f"Prefix P={p:,}")
ax.set_xlabel("Forced length F (tokens)")
ax.set_ylabel("Observed forced span D(P,F) (ms)")
ax.set_title("E14 raw grid: 4 prefixes × 6 forced lengths", loc="left", fontsize=18, weight="bold")
ax.legend(frameon=False, ncol=2, fontsize=11, loc="upper left")
style_ax(ax)
save(fig, "e14_raw_spans.png")


# E14 derived view: steady marginal fit and inferred startup decomposition.
model_path = Path("/home/lexu/we-m2-prefix-fd-sweep/models/qwen3_1p7b-e2e-pdSeparate/request_config/e14_prefix_fd_sweep/e14_grid/e14_model.json")
model = json.loads(model_path.read_text())
steady = [s for s in model["segments"] if not s["startup_transition"]]
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13.4, 5.8), gridspec_kw={"width_ratios": [1.25, 1]})
for color, p in zip(colors, grid["prefixes"]):
    seg = [s for s in steady if s["prefix_tokens"] == p]
    ax1.scatter([s["absolute_pos_mid"] for s in seg], [s["marginal_us_per_token"] for s in seg],
                s=55, color=color, label=f"P={p:,}")
x = np.linspace(0, 12288, 300)
a = model["fit"]["intercept_us"]
b = model["fit"]["slope_us_per_position"]
ax1.plot(x, a + b*x, color=VIOLET, linewidth=2.5, label="Least-squares fit")
ax1.set_xlabel("Mean absolute KV position")
ax1.set_ylabel("Adjacent-span marginal (µs/token)")
ax1.set_title("16 steady segments", loc="left", fontsize=17, weight="bold")
ax1.legend(frameon=False, fontsize=9.5, ncol=2)
style_ax(ax1)

pvals = np.array([256, 1024, 4096, 8192])
fill = np.array([0.510, 0.532, 0.620, 0.737])
tail = np.array([0.121, 0.121, 0.120, 0.119])
ready = np.array([21.406, 25.774, 109.649, 223.355])
idx = np.arange(len(pvals))
ax2.bar(idx, ready, color="#E9F0FE", edgecolor=BLUE, label="Ready residual (inferred)")
ax2.bar(idx, fill, bottom=ready, color="#F2EDFD", edgecolor=VIOLET, label="Fill estimate")
ax2.bar(idx, tail, bottom=ready+fill, color="#E5F4EE", edgecolor=GREEN, label="Tail estimate")
ax2.set_xticks(idx, [f"{p:,}" for p in pvals])
ax2.set_xlabel("Prefix P")
ax2.set_ylabel("F=1 span decomposition (ms)")
ax2.set_title("Implementation-based inference", loc="left", fontsize=17, weight="bold")
ax2.legend(frameon=False, fontsize=9.5, loc="upper left")
style_ax(ax2)
fig.suptitle("Derived views — not additional direct measurements", x=0.08, ha="left", fontsize=12, color=MUTED)
save(fig, "e14_model_decomposition.png")


# E10/E10D: all five cancellation checks and the two direct total-latency witnesses.
hist = np.array([512, 1024, 2048, 4096, 8192])
ingress = np.array([46.24, 56.14, 85.69, 169.89, 338.27])
cancel_ratio = np.array([0.999, 0.983, 0.982, 0.979, 0.972])
direct_hist = np.array([512, 1024])
lane_a = np.array([57.32, 96.96])
lane_b = np.array([65.29, 76.31])
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13.4, 5.8), gridspec_kw={"width_ratios": [1.05, 1]})
ax1.plot(hist, cancel_ratio, color=BLUE, marker="o", linewidth=2.5, markersize=7)
for x0, y0, im in zip(hist, cancel_ratio, ingress):
    ax1.annotate(f"I={im:.1f} ms", (x0, y0), xytext=(0, 9), textcoords="offset points",
                 ha="center", fontsize=9.5, color=BODY)
ax1.axhline(1.0, color=MUTED, linestyle="--", linewidth=1.3)
ax1.set_ylim(0.95, 1.01)
ax1.set_xscale("log", base=2)
ax1.set_xticks(hist, [f"{x:,}" for x in hist])
ax1.set_xlabel("Reloaded history tokens")
ax1.set_ylabel("Measured post-ingress forced / E9 prediction")
ax1.set_title("E10 component validation", loc="left", fontsize=17, weight="bold")
style_ax(ax1)

w = 0.34
ii = np.arange(2)
ax2.bar(ii-w/2, lane_a, width=w, color="#F2EDFD", edgecolor=VIOLET, label="A: recompute")
ax2.bar(ii+w/2, lane_b, width=w, color="#E9F0FE", edgecolor=BLUE, label="B: reload + delta")
for xpos, vals in [(ii-w/2, lane_a), (ii+w/2, lane_b)]:
    for x0, y0 in zip(xpos, vals):
        ax2.text(x0, y0+2, f"{y0:.2f}", ha="center", fontsize=10.5, color=INK)
ax2.set_xticks(ii, ["History 512", "History 1,024"])
ax2.set_ylabel("Direct total latency (ms)")
ax2.set_title("E10D direct witnesses", loc="left", fontsize=17, weight="bold")
ax2.legend(frameon=False, fontsize=10)
style_ax(ax2)
save(fig, "e10_raw_validation.png")


# Lane A vs B: direct bracketing witnesses beside the projected model crossing.
boundary_path = Path("/home/lexu/we-m2-prefix-fd-sweep/models/qwen3_1p7b-e2e-pdSeparate/request_config/e14_prefix_fd_sweep/e14_grid/e14_boundaries.json")
boundary = json.loads(boundary_path.read_text())
anchor_p = np.array([r["prefix_tokens"] for r in boundary["startup_anchors"]], dtype=float)
anchor_d = np.array([r["fd_span_f256_us"] for r in boundary["startup_anchors"]], dtype=float)
anchor_h = np.array([r["payload_tokens"] for r in boundary["ingress_anchors"]], dtype=float)
anchor_i = np.array([r["span_us"] for r in boundary["ingress_anchors"]], dtype=float)
a_us = float(boundary["forced_model"]["a_us"])
b_us = float(boundary["forced_model"]["b_us_per_position"])


def startup_us(p):
    return np.interp(p, anchor_p, anchor_d)


def ingress_us(h):
    return np.interp(h, anchor_h, anchor_i)


def forced_span_us(p, f):
    count = f - 256.0
    position_sum = count * p + (256.0 + f - 1.0) * count / 2.0
    return startup_us(p) + count * a_us + b_us * position_sum


s0, lnew = 256.0, 256.0
h_curve = np.linspace(256, 1536, 900)
a_curve = np.array([forced_span_us(s0, h+lnew) for h in h_curve]) / 1000.0
b_curve = np.array([ingress_us(h) + forced_span_us(s0+h, lnew) for h in h_curve]) / 1000.0
h_star = float(boundary["boundaries"][0]["delta_reload"]["crossing_tokens"])
y_star = forced_span_us(s0, h_star+lnew) / 1000.0

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13.4, 5.8), gridspec_kw={"width_ratios": [0.9, 1.25]})
ii = np.arange(2)
w = 0.34
ax1.bar(ii-w/2, lane_a, width=w, color="#F2EDFD", edgecolor=VIOLET, label="A: recompute")
ax1.bar(ii+w/2, lane_b, width=w, color="#E9F0FE", edgecolor=BLUE, label="B: reload + delta")
for xpos, vals in [(ii-w/2, lane_a), (ii+w/2, lane_b)]:
    for x0, y0 in zip(xpos, vals):
        ax1.text(x0, y0+2, f"{y0:.2f}", ha="center", fontsize=10.5)
ax1.set_xticks(ii, ["H=512", "H=1,024"])
ax1.set_ylabel("E10D offset-controlled total (ms)")
ax1.set_title("Direct witnesses bracket the flip", loc="left", fontsize=14.5, weight="bold")
ax1.text(0, 7, "A lower", ha="center", color=VIOLET, weight="bold", fontsize=11)
ax1.text(1, 7, "B lower", ha="center", color=BLUE, weight="bold", fontsize=11)
ax1.legend(frameon=False, fontsize=10, loc="upper left")
style_ax(ax1)

ax2.axvspan(256, h_star, color="#F2EDFD", alpha=0.65)
ax2.axvspan(h_star, 1536, color="#E9F0FE", alpha=0.55)
ax2.plot(h_curve, a_curve, color=VIOLET, linewidth=3, label="A = D(S, H+Lnew)")
ax2.plot(h_curve, b_curve, color=BLUE, linewidth=3, label="B = I(H)+D(S+H, Lnew)")
ax2.scatter([h_star], [y_star], s=95, color=INK, zorder=5)
ax2.axvline(h_star, color=INK, linestyle="--", linewidth=1.5)
ax2.annotate(f"Projected crossing\nH*={h_star:.0f}", (h_star, y_star),
             xytext=(34, -50), textcoords="offset points", fontsize=11, weight="bold",
             arrowprops=dict(arrowstyle="->", color=INK, linewidth=1.2))
ax2.text(410, 145, "A lower", color=VIOLET, weight="bold", fontsize=12)
ax2.text(1210, 145, "B lower", color=BLUE, weight="bold", fontsize=12)
ax2.set_xlabel("History to recover H (tokens)")
ax2.set_ylabel("Projected resume span (ms)")
ax2.set_title("Models locate the crossing", loc="left", fontsize=14.5, weight="bold")
ax2.legend(frameon=False, fontsize=9.5, loc="upper left")
style_ax(ax2)
fig.suptitle("Setting: starting prefix S=256, Lnew=256, delta reload", x=0.08, ha="left", fontsize=12, color=MUTED)
save(fig, "lane_ab_crossing.png")


# E12a: direct resident-prefill compute alongside comparison estimates.
labels = ["History 7,936\nDelta 256", "History 7,168\nDelta 1,024"]
prefill_compute = np.array([292.935, 409.636])
# Current Lane B reloads the complete target KV state. It therefore has no
# force-decode reconstruction, and both 8,192-context cases pay the same E5
# full-KV ingress span.
lane_b_compute = np.array([0.0, 0.0])
lane_b_total = np.array([338.266, 338.266])
lane_c_total = np.array([654.765, 929.693])
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13.4, 5.8))
ii = np.arange(2)
w = 0.34
ax1.bar(ii-w/2, prefill_compute, width=w, color="#F2EDFD", edgecolor=VIOLET,
        label="Lane C: resident prefill — measured S6a")
ax1.bar(ii+w/2, lane_b_compute, width=w, color="#E9F0FE", edgecolor=BLUE,
        label="Lane B: full-KV reload — no recompute")
for xpos, vals in [(ii-w/2, prefill_compute), (ii+w/2, lane_b_compute)]:
    for x0, y0 in zip(xpos, vals):
        ax1.text(x0, y0+10, f"{y0:.1f}", ha="center", fontsize=10.5,
                 color=BLUE if y0 == 0 else INK, weight="bold" if y0 == 0 else "normal")
ax1.set_xticks(ii, labels)
ax1.set_ylabel("Compute span (ms)")
ax1.set_title("On-card reconstruction compute", loc="left", fontsize=17, weight="bold")
ax1.legend(frameon=False, fontsize=9.5)
style_ax(ax1)

ax2.bar(ii-w/2, lane_b_total, width=w, color="#E9F0FE", edgecolor=BLUE,
        label="Lane B: reload complete 8,192-token KV")
ax2.bar(ii+w/2, lane_c_total, width=w, color="#E5F4EE", edgecolor=GREEN, label="Lane C serial — derived")
for xpos, vals in [(ii-w/2, lane_b_total), (ii+w/2, lane_c_total)]:
    for x0, y0 in zip(xpos, vals):
        ax2.text(x0, y0+20, f"{y0:.1f}", ha="center", fontsize=10.5)
ax2.set_xticks(ii, labels)
ax2.set_ylabel("Resume latency estimate (ms)")
ax2.set_title("Resume-to-KV-ready composition", loc="left", fontsize=17, weight="bold")
ax2.legend(frameon=False, fontsize=9.5)
style_ax(ax2)
fig.suptitle("Both cases end at context 8,192; common next free-decode is excluded",
             x=0.08, ha="left", fontsize=12, color=MUTED)
save(fig, "e12a_screening.png")
