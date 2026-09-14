#!/usr/bin/env python3
"""Request length distributions of the three workload traces used in the
KV / decoder-lever analyses (Claude Code, Mooncake, ServeGen), as
percentile range strips on a log axis.

Reads the sibling studies' raw/result files; writes results/lengths.json
and results/trace_length_distributions.png.
"""
import csv, json, os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
GC = os.path.join(ROOT, "2026-09-02-gc-trace-study", "results", "steps.csv")
MC = os.path.join(ROOT, "2026-09-03-mooncake-trace-study", "data")
SG = os.path.join(ROOT, "2026-09-05-servegen-trace-study", "results", "lengths.json")
PS = ("p10", "p50", "p90", "p99", "max")


def pct(a):
    a = np.asarray(a, float)
    return dict(zip(PS, [float(np.percentile(a, 10)), float(np.percentile(a, 50)),
                         float(np.percentile(a, 90)), float(np.percentile(a, 99)), float(a.max())]))


rows = []  # (family, label, input_pcts, output_pcts, n)
gc = list(csv.DictReader(open(GC)))
for label, sc in (("Claude Code · main thread", "0"), ("Claude Code · subagents", "1")):
    sel = [r for r in gc if r["sidechain"] == sc]
    rows.append(("claude", label, pct([int(r["context"]) for r in sel]),
                 pct([int(r["output"]) for r in sel]), len(sel)))
for label, fn in (("Mooncake · conversation", "conversation_trace.jsonl"),
                  ("Mooncake · toolagent", "toolagent_trace.jsonl"),
                  ("Mooncake · synthetic", "synthetic_trace.jsonl")):
    il, ol = [], []
    for line in open(os.path.join(MC, fn)):
        d = json.loads(line); il.append(d["input_length"]); ol.append(d["output_length"])
    rows.append(("mooncake", label, pct(il), pct(ol), len(il)))
sg = json.load(open(SG))
for key, label in (("deepseek-r1", "ServeGen · DeepSeek-R1"), ("m-large (Qwen-Max)", "ServeGen · Qwen-Max"),
                   ("m-mid (Qwen-Plus)", "ServeGen · Qwen-Plus"), ("m-small (Qwen-Turbo)", "ServeGen · Qwen-Turbo")):
    def sub(d): return {"p10": None, "p50": d["p50"], "p90": d["p90"], "p99": d["p99"], "max": d["max"]}
    rows.append(("servegen", label, sub(sg[key]["input_tokens"]), sub(sg[key]["output_tokens"]),
                 int(sg[key]["expected_requests_in_trace"])))

json.dump([{"family": f, "trace": l, "n": n, "input_tokens": i, "output_tokens": o} for f, l, i, o, n in rows],
          open(os.path.join(HERE, "results", "lengths.json"), "w"), indent=1)

# ---- figure: two percentile strips, log x -----------------------------------
COL = {"claude": "#2a78d6", "mooncake": "#d2477f", "servegen": "#eda100"}  # validated palette
INK, INK2, GRID, BG = "#1a1a19", "#4a4a47", "#e4e4e1", "#fcfcfb"
fig, axes = plt.subplots(1, 2, figsize=(13.2, 5.4), dpi=170, sharey=True)
fig.patch.set_facecolor(BG)
ys = np.arange(len(rows))[::-1].astype(float)
# gap between families
gap = 0
for i, (f, *_r) in enumerate(rows):
    if i and f != rows[i - 1][0]:
        gap += 1
    ys[i] -= gap * 0.6 * -1  # push later families down (ys descending)
ys = ys - np.array([sum(1 for j in range(1, i + 1) if rows[j][0] != rows[j - 1][0]) for i in range(len(rows))]) * 0.7

for ax, which, title in ((axes[0], 2, "Input context per request (tokens)"),
                         (axes[1], 3, "Output / decode length per request (tokens)")):
    ax.set_facecolor(BG)
    for (f, label, ip, op, n), y in zip(rows, ys):
        d = (ip, op)[which - 2]; c = COL[f]
        lo = d["p10"] if d["p10"] is not None else d["p50"]
        ax.plot([lo, d["p99"]], [y, y], color=c, lw=2, solid_capstyle="round", zorder=2)
        ax.plot([d["p99"], d["max"]], [y, y], color=c, lw=0.9, ls=(0, (1, 2)), zorder=2)
        if d["p10"] is not None:
            ax.plot(d["p10"], y, marker="|", ms=9, color=c, mew=1.5, zorder=3)
        ax.plot(d["p50"], y, "o", ms=8, color=c, mec=BG, mew=1.2, zorder=4)
        ax.plot(d["p90"], y, "o", ms=6.5, mfc=BG, mec=c, mew=1.8, zorder=4)
        ax.plot(d["p99"], y, marker="|", ms=9, color=c, mew=1.5, zorder=3)
        ax.plot(d["max"], y, marker="x", ms=5, color=c, mew=1.2, zorder=3)
        ax.text(d["p50"], y + 0.32, f"{d['p50']:,.0f}", ha="center", va="bottom", fontsize=7.3, color=INK2)
    ax.set_xscale("log"); ax.set_xlim(1, 3e6)
    ax.set_title(title, fontsize=10.5, loc="left", color=INK, pad=10)
    ax.grid(axis="x", color=GRID, lw=0.7); ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color("#c9c9c6"); ax.tick_params(axis="both", colors=INK2, labelsize=8.5, length=0)
    ax.set_xticks([1, 10, 100, 1e3, 1e4, 1e5, 1e6]); ax.set_xticklabels(["1", "10", "100", "1K", "10K", "100K", "1M"])
    ax.xaxis.set_minor_locator(matplotlib.ticker.NullLocator())

# on-chip capacity references on the input panel
ax = axes[0]
for x, txt, ha, dx in ((29184, "placed-region KV ceiling 29,184 (measured)", "right", 0.94),
                       (29184 + 74000, "+ unplaced SRAM ≈ 103K [derived]", "left", 1.06)):
    ax.axvline(x, color="#8a8a85", lw=1.0, ls="--", zorder=1)
    ax.text(x * dx, ys[0] + 1.05, txt, fontsize=7.4, color=INK2, va="bottom", ha=ha)
ax.set_yticks(ys); ax.set_yticklabels([r[1] for r in rows], fontsize=8.8, color=INK)
axes[0].set_ylim(ys[-1] - 0.8, ys[0] + 1.9)

# legend for the marks
from matplotlib.lines import Line2D
h = [Line2D([], [], marker="|", color=INK2, ls="none", ms=9, mew=1.5, label="p10 (Claude Code, Mooncake only)"),
     Line2D([], [], marker="o", color=INK2, ls="none", ms=8, label="p50"),
     Line2D([], [], marker="o", mfc=BG, mec=INK2, ls="none", ms=6.5, mew=1.8, label="p90"),
     Line2D([], [], marker="|", color=INK2, ls="none", ms=9, mew=1.5, label="p99"),
     Line2D([], [], marker="x", color=INK2, ls="none", ms=5, label="max")]
fig.legend(handles=h, loc="lower center", ncol=5, frameon=False, fontsize=8.4, bbox_to_anchor=(0.5, -0.01))
fig.suptitle("Request length distributions of the three workload traces (per API call / request)",
             fontsize=12, x=0.01, ha="left", color=INK)
fig.text(0.01, 0.925, "Claude Code: one user, 46,650 calls (26,144 main + 20,506 subagent), 2026-08-04→09-02 · "
         "Mooncake: Kimi 2024, 39,632 requests, output hard-capped at 2,000 · "
         "ServeGen: Alibaba Model Studio, per-model length samples (no p10 published)",
         fontsize=7.8, color=INK2)
fig.tight_layout(rect=(0, 0.04, 1, 0.92))
out = os.path.join(HERE, "results", "trace_length_distributions.png")
fig.savefig(out, bbox_inches="tight", facecolor=BG)
print("wrote", out)
