#!/usr/bin/env python3
"""Transport vs CE decomposition of the on-chip tier, with the knob that
moves each class. All bars device-measured except the wire floor (spec)."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BLUE, PURPLE, GRAY = "#1a56db", "#7048e8", "#98a2b3"
fig = plt.figure(figsize=(13.6, 6.8))

# ---------------- left: per-word cost ladder, colored by class
axl = fig.add_axes([0.205, 0.10, 0.325, 0.80])
axl.set_facecolor("#fafafa")
items = [  # (label, cyc/word, class, note)
    ("wire throughput floor", 1.0, "wire", "spec: 1 word/cyc/link"),
    ("v4 fwd tax · task", 1.06, "wire", "measured"),
    ("v4 fwd tax · dsd", 1.29, "wire", "measured"),
    ("storage emit loop (sync @mov32)", 13.0, "ce", "measured"),
    ("row-0 reload relay", 28.8, "ce", "measured"),
    ("storage park receive (task)", 43.3, "ce", "measured"),
    ("owner reload receive (task)", 43.6, "ce", "measured; dsd -> ~0 exposed"),
    ("row-0 receive + forward", 75.4, "ce", "measured"),
]
ys = range(len(items))
for y, (lb, v, cls, note) in zip(ys, items):
    c = BLUE if cls == "wire" else PURPLE
    axl.barh(y, v, color=c, height=0.62, alpha=0.35 if lb.startswith("wire") else 0.95)
    axl.text(v + 1.2, y, f"{v:g}", va="center", fontsize=11.5, fontweight="bold")
    if "spec" in note or "dsd" in note:
        axl.text(v + 11, y, note, va="center", fontsize=8.8, color="#888888")
axl.set_yticks(list(ys))
axl.set_yticklabels([i[0] for i in items], fontsize=10.6)
axl.invert_yaxis()
axl.set_xlim(0, 92)
axl.set_xlabel("cycles per word", fontsize=12)
axl.set_title("Every per-word cost, by class", fontsize=14, fontweight="bold", loc="left")
axl.grid(axis="x", color="#e0e0e0", lw=0.6)
for sp in ("top", "right"):
    axl.spines[sp].set_visible(False)
axl.text(26, 2.0, "transport (router/wire)", color=BLUE, fontsize=12, fontweight="bold")
axl.text(60, 4.6, "CE send/recv", color=PURPLE, fontsize=12, fontweight="bold")

# ---------------- right: the knob that moves each class
axr = fig.add_axes([0.565, 0.02, 0.425, 0.94]); axr.axis("off")
axr.set_xlim(0, 1); axr.set_ylim(0, 1); axr.set_autoscale_on(False)
def block(y, title, color, lines):
    axr.text(0.02, y, title, fontsize=13, fontweight="bold", color=color)
    for j, ln in enumerate(lines):
        axr.text(0.04, y - 0.055 - j * 0.048, ln, fontsize=10.6)
block(0.95, "TRANSPORT — knob: storage-PE placement", BLUE, [
    "measured: t_hop = 2.0 cyc/hop, NO per-word term (Exp-C, D up to 32)",
    "⇒ strip placement is latency-free; depth budget is capacity/routing",
    "unmeasured: link sharing with live decode, multi-lane aggregation",
    "(all runs so far are isolated single-lane)",
])
block(0.62, "CE — knob 1: thread model (task → DSD)", PURPLE, [
    "owner receive: 43.6 → ~0 exposed  (Exp-B, measured)",
    "storage park receive 43.3 and emit 13.0 are still task/sync-loop:",
    "the next rung; projected ~4-5x on the tier marginal (projection)",
])
block(0.36, "CE — knob 2: allocation across CEs", PURPLE, [
    "v5 concentrates: row-0 CE handles ALL N·E words (44-75 cyc each)",
    "while deeper rows' CEs idle — tax 30.7-47.0",
    "v4 distributes: each row's CE touches only its own band (bh·E);",
    "inter-row movement is routers — tax 1.06-1.29",
    "⇒ the 25-35x tax gap IS the allocation decision, measured",
])
fig.savefig(__file__.rsplit("/", 1)[0] + "/fig_router_vs_ce.png", dpi=175)
print("router-vs-ce decomposition written")
