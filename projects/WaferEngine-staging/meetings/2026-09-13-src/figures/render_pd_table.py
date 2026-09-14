"""Render the prefix × decode spectrum table (Round 171) as a figure for a wafer-slides `figure` slide.
House tokens from wafer_theme.py; text in ink tokens only; best cell per row gets the violet tint."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Rectangle

INK, BODY, MUTED, ACCENT, RULE, CARD, TINT = "#18181B", "#52525B", "#A1A1AA", "#6D28D9", "#E4E4E7", "#F4F4F5", "#F2EDFD"

font_manager.fontManager.addfont(font_manager.findfont("Noto Sans CJK SC")) if False else None
plt.rcParams["font.family"] = ["Noto Sans CJK SC", "Noto Sans CJK HK", "Droid Sans Fallback", "DejaVu Sans"]

cols = ["Scenario (prefix / decode)", "prefix", "decode", "KV GB", "CS-3 alone", "PD-split", "H100 alone", "GPU-streamed", "best", "decode share"]
rows = [
 ["Qwen-Turbo p50 (short / tiny)", "680", "11", "0.10", "82", "21", "61", "28", "PD", "48%"],
 ["ServeGen R1 p50 (short / long)", "208", "792", "0.03", "745", "726", "3,654", "888", "PD", "100%"],
 ["Long reasoning (short / very long)", "208", "10,000", "0.03", "9,147", "9,128", "46,105", "11,172", "PD", "100%"],
 ["R1 p90", "2,100", "3,400", "0.31", "3,462", "3,273", "16,020", "10,290", "PD", "99%"],
 ["Qwen-Max p90 (mid / short)", "2,400", "433", "0.35", "668", "453", "2,078", "1,472", "PD", "92%"],
 ["Mooncake conv p50", "6,900", "350", "1.02", "1,096", "482", "1,834", "2,850", "PD", "77%"],
 ["Mooncake toolagent p90", "17,000", "507", "2.51", "2,435", "1,012", "3,103", "9,468", "PD", "64%"],
 ["Long-doc classification (long / tiny)", "27,000", "20", "3.98", "2,872", "734", "796", "1,238", "PD", "4%"],
 ["Mooncake conv p90 (long / short)", "27,000", "597", "3.98", "3,730", "1,592", "4,212", "17,411", "PD", "56%"],
 ["Mooncake conv p99", "85,000", "1,100", "12.5", "no fit", "no fit", "12,075", "97,363", "H100", "80%"],
 ["Claude Code median", "197,000", "5,800", "29.1", "no fit", "no fit", "88,215", "1,158,677", "H100", "94%"],
]
best_col = {"PD": 5, "H100": 6}
widths = [2.9, 0.9, 0.9, 0.8, 1.05, 1.05, 1.1, 1.35, 0.9, 1.15]

W, H = 17.0, 6.2
fig = plt.figure(figsize=(W, H), dpi=200)
ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, W); ax.set_ylim(0, H); ax.axis("off")

x0 = 0.15; total = sum(widths); scale = (W - 0.3) / total
xs = [x0]
for w in widths: xs.append(xs[-1] + w * scale)
n = len(rows); header_h = 0.5; row_h = (H - header_h - 0.2) / n
y_top = H - 0.1

# header
for j, c in enumerate(cols):
    ha = "left" if j == 0 else "right"
    xx = xs[j] + 0.05 if j == 0 else xs[j + 1] - 0.08
    ax.text(xx, y_top - header_h / 2, c.upper(), ha=ha, va="center", fontsize=12, color=MUTED)
ax.plot([x0, W - 0.15], [y_top - header_h] * 2, color=RULE, lw=0.8)

for i, r in enumerate(rows):
    yc = y_top - header_h - (i + 0.5) * row_h
    bc = best_col[r[8]]
    ax.add_patch(Rectangle((xs[bc] + 0.03, yc - row_h / 2 + 0.05), xs[bc + 1] - xs[bc] - 0.06, row_h - 0.1, facecolor=TINT, edgecolor="none"))
    for j, v in enumerate(r):
        ha = "left" if j == 0 else "right"
        xx = xs[j] + 0.05 if j == 0 else xs[j + 1] - 0.08
        col = INK if j == 0 else BODY
        weight = "normal"
        if v == "no fit": col = MUTED
        if j == bc: col, weight = ACCENT, "bold"
        if j == 8: col = ACCENT if v == "PD" else BODY
        ax.text(xx, yc, v, ha=ha, va="center", fontsize=14 if j == 0 else 13.5, color=col, fontweight=weight)
    ax.plot([x0, W - 0.15], [yc - row_h / 2] * 2, color=RULE, lw=0.6)

fig.savefig("pd_split_spectrum_table.png", dpi=200, facecolor="white")
print("ok")
