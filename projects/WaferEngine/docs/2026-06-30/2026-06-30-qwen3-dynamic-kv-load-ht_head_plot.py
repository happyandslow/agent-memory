import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, Rectangle

P = 8          # P_BLOCK_SIZE rows (Y, vocab-shard)
W = P // 2     # HT_WIDTH_head cols (X, hidden-shard) = 4
diag_col = lambda py: py // 2          # col x owns rows 2x, 2x+1

C1 = "#1f77b4"   # pre_embed_x (host X in)  -> blue
C2 = "#2ca02c"   # post_embed_x (-> row_0)  -> green
GA = "#ff7f0e"   # UP/DOWN W_E gather       -> orange
DIAGFC = "#d6e4f0"

def draw_grid(ax, title):
    ax.set_title(title, fontsize=11, pad=10)
    for py in range(P):
        for x in range(W):
            is_d = (diag_col(py) == x)
            ax.add_patch(Rectangle((x-0.42, py-0.42), 0.84, 0.84,
                         facecolor=(DIAGFC if is_d else "white"),
                         edgecolor="#999", lw=1.0, zorder=1))
            if is_d:
                ax.text(x, py, "D", ha="center", va="center",
                        fontsize=9, fontweight="bold", color="#13406b", zorder=3)
            else:
                ax.text(x, py, "·", ha="center", va="center",
                        fontsize=9, color="#bbb", zorder=3)
    ax.set_xlim(-1.7, W+1.4)
    ax.set_ylim(P-0.3, -1.3)        # row 0 at top
    ax.set_xticks(range(W)); ax.set_xticklabels([f"col{ x}" for x in range(W)], fontsize=8)
    ax.set_yticks(range(P)); ax.set_yticklabels([f"row{py}" for py in range(P)], fontsize=8)
    ax.set_xlabel("X  (hidden-dim shard)", fontsize=9)
    ax.set_ylabel("Y  (vocab shard / dim-on-Y of X vector)", fontsize=9)
    for s in ax.spines.values(): s.set_visible(False)
    ax.tick_params(length=0)

def arrow(ax, x0, y0, x1, y1, color, ls="-", lw=2.0, z=2):
    ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1),
                 arrowstyle="-|>", mutation_scale=12,
                 color=color, lw=lw, linestyle=ls, zorder=z,
                 shrinkA=0, shrinkB=2))

# ---------------- Panel A: C1 -> diag -> C2  (the KV-load reuse path) ----------
fig, (axA, axB) = plt.subplots(1, 2, figsize=(13.5, 6.2))

draw_grid(axA, "Reused for KV load:  C1 → diag → C2   (per-row HORIZONTAL, all rows in parallel)")
for py in range(P):
    dc = diag_col(py)
    # C1: west edge -> diag col (WEST->EAST relay, WEST->RAMP at diag)
    arrow(axA, -1.5, py, dc-0.42, py, C1)
    # C2: diag -> east edge -> row_0
    arrow(axA, dc+0.42, py, W+0.5, py, C2, lw=2.0)
    axA.text(W+0.62, py, f"→row_0 PE{py}", ha="left", va="center",
             fontsize=7.5, color=C2)
axA.text(-1.5, -0.95, "host X in (demux)", color=C1, fontsize=8, ha="left")
# legend
axA.plot([], [], color=C1, lw=2.4, label="C1  pre_embed_x (id 18): WEST→EAST, drained (RAMP) at diag")
axA.plot([], [], color=C2, lw=2.4, label="C2  post_embed_x (id 23): diag RAMP→EAST → row_0")
axA.add_patch(Rectangle((0,0),0,0, facecolor=DIAGFC, edgecolor="#999", label="D = diagonal PE (col x ⇔ rows 2x, 2x+1)"))
axA.legend(loc="lower center", bbox_to_anchor=(0.5, -0.30), fontsize=7.8, frameon=False)

# ---------------- Panel B: + UP/DOWN vertical gather (embedding only) ----------
draw_grid(axB, "Embedding ADDS:  UP/DOWN W_E gather   (VERTICAL, cross-row)  —  SKIPPED for KV")
# faded C1/C2 for context
for py in range(P):
    dc = diag_col(py)
    arrow(axB, -1.5, py, dc-0.42, py, C1, lw=1.0);
    arrow(axB, dc+0.42, py, W+0.5, py, C2, lw=1.0)
# illustrate vertical gather converging on each column's diag pair
# (token's vocab row py_b sends W_E up/down to that col's diag PE)
examples = {1: 6, 2: 1}   # col -> example source row py_b (runtime-dependent)
for x, src in examples.items():
    dpy = 2*x  # upper-diag of col x
    if src > dpy:   # source below diag -> UP chain (north)
        arrow(axB, x, src-0.42, x, dpy+0.42, GA, ls=(0,(4,2)), lw=2.2)
        axB.text(x+0.12, (src+dpy)/2, "UP", color=GA, fontsize=7.5, va="center")
    else:           # source above diag -> DOWN chain (south)
        arrow(axB, x, src+0.42, x, dpy-0.42+1, GA, ls=(0,(4,2)), lw=2.2)
        axB.text(x+0.12, (src+dpy)/2, "DOWN", color=GA, fontsize=7.5, va="center")
    axB.text(x, src, "src\nW_E", ha="center", va="center", fontsize=6.5, color=GA, zorder=4)
axB.plot([], [], color=GA, lw=2.2, ls="--", label="UP_A/B (21/22) · DOWN_A/B (8/9): N/S W_E gather to diag")
axB.plot([], [], color=C1, lw=1.0, label="C1/C2 (faded — same as left)")
axB.legend(loc="lower center", bbox_to_anchor=(0.5, -0.26), fontsize=7.8, frameon=False)

fig.suptitle("HT_head data-transfer directions  (example P_BLOCK_SIZE=8 rows × HT_WIDTH_head=4 cols)",
             fontsize=12.5, y=0.99)
fig.tight_layout(rect=[0, 0.02, 1, 0.96])
out = "/tmp/claude-1023/-home-lexu-WaferEngine/0a2f4f2a-22d7-434c-9ecd-d3779650fa36/scratchpad/ht_head_dataflow.png"
fig.savefig(out, dpi=130, bbox_inches="tight")
print("saved", out)
