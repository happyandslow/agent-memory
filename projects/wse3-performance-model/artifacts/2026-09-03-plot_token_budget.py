#!/usr/bin/env python3
"""Per-token time budget, one wafer vs two — four categories only.

Numbers from the stamped lockstep run `lock_rdma5` (A wsjob-unaadmepstdus7572thpsa,
B wsjob-jj7nok69hebkkbrbych7ww), the passthrough ring (wsjob-3xeenwcoeodyeotjcsbwoo)
and the transport bench (wsjob-pyn62skh9ikgv8g2uyull7). See
docs/analysis/2026-09-03-4b-two-wafer-pp-decode-demo.md.
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch, Rectangle

HERE = os.path.dirname(os.path.abspath(__file__))
C_WAFER, C_SDK, C_HOST, C_WIRE, C_REST = "#2a78d6", "#d2477f", "#eda100", "#087f5b", "#d9d9d6"

# (label, µs, category) in time order for one token
TWO = [("", 18, "host"), ("SDK", 114, "sdk"), ("wafer A · 18 layers", 488, "wafer"),
       ("", 14, "wire"), ("SDK", 135, "sdk"), ("wafer B · 18 layers + lm_head", 585, "wafer"),
       ("", 6, "host"), ("", 23, "rest")]
ONE = [("wafer · 36 layers + lm_head", 1036, "wafer")]
COL = {"wafer": C_WAFER, "sdk": C_SDK, "host": C_HOST, "wire": C_WIRE, "rest": C_REST}

fig, ax = plt.subplots(figsize=(13.6, 4.3), dpi=170)
fig.patch.set_facecolor("#fcfcfb"); ax.set_facecolor("#fcfcfb")


def bar(y, segs, h=0.60):
    x = 0.0
    for lab, v, cat in segs:
        ax.add_patch(Rectangle((x, y - h / 2), v, h, facecolor=COL[cat], edgecolor="#fcfcfb", lw=1.6))
        if v >= 100:
            ax.text(x + v / 2, y, f"{lab}\n{v:,} µs" if lab else f"{v:,} µs", ha="center", va="center",
                    fontsize=8.8, color="white", linespacing=1.5)
        x += v
    return x


t1 = bar(1.0, ONE)
t2 = bar(0.0, TWO)
ax.text(t1 + 18, 1.0, f"{t1:,.0f} µs / token   ·   965 tok/s", va="center", fontsize=9.5, color="#1a1a19")
ax.text(t2 + 18, 0.0, f"{t2:,.0f} µs / token   ·   725 tok/s   (1.33×)", va="center", fontsize=9.5,
        color="#1a1a19", fontweight="bold")
ax.text(-18, 1.0, "1 wafer", ha="right", va="center", fontsize=10.5, fontweight="bold")
ax.text(-18, 0.0, "2 wafers\n(RDMA hop)", ha="right", va="center", fontsize=10.5, fontweight="bold")

# leaders for the slivers
for x0, v, txt in [(0, 18, "host 18"), (620, 14, "RDMA 14 µs\nboth directions"), (1354, 29, "host + untimed 29")]:
    ax.annotate(txt, xy=(x0 + v / 2, -0.31), xytext=(x0 + v / 2, -0.72), ha="center", fontsize=7.6,
                color="#4a4a47", arrowprops=dict(arrowstyle="-", color="#8a8a85", lw=0.7))

tot = {"wafer": 1073, "sdk": 249, "host": 24, "wire": 14}
ax.text(0, -1.16, "two wafers, per token:   "
        + "     ".join(f"{n} {tot[k]:,} µs ({100*tot[k]/1383:.0f} %)" for k, n in
                       [("wafer", "on-wafer compute"), ("sdk", "SDK H2D+D2H"), ("host", "host"), ("wire", "wire")]),
        fontsize=9.2, color="#1a1a19", va="top")
ax.text(0, -1.56, "The extra 347 µs vs one wafer is ~250 µs of SDK stream latency (two boundaries), not the network.\n"
        "SDK block = H2D+D2H of that wafer, halves not separated; wafer B's split uses the ring floor (135 µs). "
        "Ring alone (no compute): 160 µs RTT, flat 8 B–10 KB.",
        fontsize=7.8, color="#4a4a47", va="top", linespacing=1.5)

ax.set_xlim(-250, 1720); ax.set_ylim(-1.95, 1.60)
ax.set_yticks([]); ax.set_xlabel("µs per decode token", fontsize=9.5)
ax.set_xticks(range(0, 1601, 200))
ax.tick_params(axis="x", labelsize=8.5, colors="#4a4a47")
for s in ("top", "right", "left"):
    ax.spines[s].set_visible(False)
ax.spines["bottom"].set_color("#c9c9c6")
ax.set_title("Qwen3-4B decode: where one token's time goes (CS-3, 2026-09-03, bsz 1; run lock_rdma5)", fontsize=11.5, pad=14)
ax.legend(handles=[Patch(fc=COL[k], label=v) for k, v in
                   [("wafer", "on-wafer compute"), ("sdk", "SDK H2D + D2H"), ("host", "host (embed, enqueue, parse)"),
                    ("wire", "wire (RDMA, pod-to-pod)"), ("rest", "untimed")]],
          loc="upper left", bbox_to_anchor=(0.0, 1.30), ncol=5, frameon=False, fontsize=8.6)
fig.tight_layout()
out = os.path.join(HERE, "..", "cs3", "two_wafer_pp_token_budget.png")
fig.savefig(out, bbox_inches="tight", facecolor=fig.get_facecolor())
print("wrote", os.path.abspath(out))
