#!/usr/bin/env python3
"""Two-wafer PP floorplan for the Qwen3-4B decode demo (device_pp_a / device_pp_b).

Geometry is the placement launch.py computes for both roles (PLACE_X=132,
PLACE_Y=1, P_BLOCK_SIZE=256, HT band x=3..130, KV staircase from x=645) plus the
host-stream landing spots from each run's sim_port_map.json (all on the WEST
edge: kv bands at lvds 0/18, X in at 36, Z out / logits out at 1). Per-PE SRAM
labels are the single-wafer image numbers (same ELFs per role). Companion of
qwen3-4b-decode-sram/tools/plot_floorplan.py — same colours, same conventions.
Measured numbers in the hop panel come from cs3/out_pp_*_lock_rdma1 and
cs3/bench1 (2026-09-03).
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, Rectangle, FancyBboxPatch

HERE = os.path.dirname(os.path.abspath(__file__))
FAB_W, FAB_H = 762, 1172
P, PX, PY = 256, 132, 1
HT_X, HT_W = 3, 128
STAIR = 645
GAP = 470                      # PE-units of white space between the two wafers
XB = FAB_W + GAP               # x offset of wafer B
C_ATTN, C_FFN, C_HT, C_STRIP, C_IO, C_UNUSED = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#ececea"
C_ZMUX = "#7b4fd1"
C_HOST = "#f4f1e8"
MINW = 7

fig, ax = plt.subplots(figsize=(19, 10.5), dpi=150)
fig.patch.set_facecolor("#fcfcfb"); ax.set_facecolor("#fcfcfb")


def rect(x, y, w, h, fc, ec="#fcfcfb", lw=0.8, ls="-", z=2, alpha=1.0):
    ax.add_patch(Rectangle((x, y), w, h, facecolor=fc, edgecolor=ec, lw=lw, ls=ls, zorder=z, alpha=alpha))


def label(x, y, s, fs=7.4, col="white", ha="center", va="center", **kw):
    ax.text(x, y, s, ha=ha, va=va, fontsize=fs, color=col, linespacing=1.35, zorder=4, **kw)


def arrow(p0, p1, colour="#1a1a19", lw=1.6, style="-|>", rad=0.0, ls="-", z=5):
    ax.add_patch(FancyArrowPatch(p0, p1, arrowstyle=style, mutation_scale=14, color=colour,
                                 lw=lw, ls=ls, connectionstyle=f"arc3,rad={rad}", zorder=z))


def num(x, y, n):
    ax.text(x, y, n, fontsize=8.5, fontweight="bold", color="#1a1a19",
            bbox=dict(boxstyle="circle,pad=0.2", fc="#fcfcfb", ec="#1a1a19", lw=0.8), zorder=6)


def wafer(ox, role):
    """Draw one wafer with origin x offset ox. role in ('a','b')."""
    rect(ox, 0, FAB_W, FAB_H, C_UNUSED, ec="#6d6d69", lw=1.0, z=1)
    layers = ["L0-8", "L9-17"] if role == "a" else ["L18-26", "L27-35"]
    rows_global = ["r0", "r1"] if role == "a" else ["r2", "r3"]
    # block rows: even row ATTN west, odd row FFN west (same serpentine as the full layout)
    for r in range(2):
        y0 = PY + r * P
        attn_x = PX if r % 2 == 0 else PX + P
        ffn_x = PX + P if r % 2 == 0 else PX
        rect(ox + attn_x, y0, P, P, C_ATTN)
        rect(ox + ffn_x, y0, P, P, C_FFN)
        label(ox + attn_x + P / 2, y0 + P / 2,
              f"ATTN {rows_global[r]} · {layers[r]}\n256×256 = 65,536 PE\nx {attn_x}–{attn_x+255}  y {y0}–{y0+255}\n37.8 KB/PE (79%)\nKV 4.6 KB · free 10.2 KB")
        label(ox + ffn_x + P / 2, y0 + P / 2,
              f"FFN {rows_global[r]} · {layers[r]}\n256×256 = 65,536 PE\nx {ffn_x}–{ffn_x+255}  y {y0}–{y0+255}\n33.8 KB/PE (70%)\nno KV · free 14.2 KB")
        # strips: west (x=131) and east (x=644); real ones carry K-pipe (row0 east, row1 east)
        rect(ox + PX - 1, y0, MINW, P, C_STRIP if r == 1 else "#f3d98a")          # west strip
        rect(ox + PX + 2 * P, y0, MINW, P, C_STRIP)                                # east strip
        # KV staircase: injector at 645+r, kv_fwd relay for r=1 at 645
        rect(ox + STAIR + r, y0, MINW, P, C_IO)
        if r > 0:
            rect(ox + STAIR, y0, MINW, P, "#f6c5d6")
    # x_demux column at x=130, rows of row 0 (both roles)
    rect(ox + PX - 2, PY, MINW, P, C_IO)
    # host lvds ports on the WEST edge (from sim_port_map.json)
    rect(ox, 0, MINW, 40, C_IO)
    if role == "a":
        # z_mux column at x=129 alongside row 1 (Z egress)
        rect(ox + PX - 3, PY + P, MINW, P, C_ZMUX)
        placed = (STAIR + 2 - (PX - 3)) * (PY + 2 * P)
        pr = (ox + PX - 3, 0, STAIR + 2 - (PX - 3), PY + 2 * P)
        title = "wafer A — device_pp_a: layers 0–17 (rows r0, r1) + x_demux + z_mux"
    else:
        rect(ox + HT_X, PY + P, HT_W, P, C_HT)
        label(ox + HT_X + HT_W / 2, PY + P + P / 2,
              "HT tail\nnorm · lm_head\ntop-k · sample\n128×256\n43.9 KB/PE (91%)\nfree 4.1 KB", fs=7.2)
        rect(ox + HT_X, PY + 2 * P, HT_W, MINW, C_IO)                          # logits_mux row y=513
        placed = (STAIR + 2 - HT_X) * (PY + 2 * P + 1)
        pr = (ox + HT_X, 0, STAIR + 2 - HT_X, PY + 2 * P + 1)
        title = "wafer B — device_pp_b: layers 18–35 (rows r2, r3) + x_demux + HT tail + logits_mux"
    rect(*pr, "none", ec="#6d6d69", lw=0.8, ls="--", z=3)
    label(pr[0] + pr[2] - 4, pr[1] + pr[3] + 28, f"placed rectangle {pr[2]}×{pr[3]} = {placed:,} PEs",
          fs=8, col="#4a4a47", ha="right", va="top")
    idle = FAB_W * FAB_H - placed
    label(ox + FAB_W - 8, FAB_H - 12, f"unplaced fabric\n≈{idle/1000:.0f}K PEs ≈ {idle*49152/2**30:.1f} GiB SRAM idle",
          fs=8, col="#4a4a47", ha="right", va="bottom")
    label(ox + FAB_W / 2, -78, title, fs=9.5, col="#1a1a19", fontweight="bold")
    return pr


prA = wafer(0, "a")
prB = wafer(XB, "b")

# ---------------- on-wafer flow arrows ----------------
# A: 1 host X -> x_demux -> ATTN r0 ; 2 ATTN<->FFN r0 ; 3 K-pipe r0->r1 (east) ; 4 FFN r1 -> west strip -> z_mux
arrow((0 + MINW, 36), (PX - 2, 36))                                    # host port -> x_demux (W edge)
arrow((PX - 2 + MINW, 128), (PX + 60, 128))                            # x_demux -> ATTN r0
arrow((PX + 200, 23), (PX + P + 60, 23)); arrow((PX + P + 60, 237), (PX + 200, 237))
arrow((PX + 2 * P, 237), (PX + 2 * P, 257 + 22)); arrow((PX + 2 * P, 257 + 22), (PX + P + 200, 257 + 22))
arrow((PX + P + 60, 257 + 236), (PX + 200, 257 + 236))                 # A row1 FFN->ATTN(B back)... simplified
arrow((PX + 200, 257 + 22), (PX + P + 60, 257 + 22))
arrow((PX + 40, 257 + 236), (PX - 3 + MINW, 257 + 236))               # FFN r1 -> z_mux
arrow((PX - 3, 257 + 236), (PX - 3, 257 + 20)); arrow((PX - 3, 257 + 20), (MINW + 2, 20))   # z_mux north -> host port
num(150, 100, "1"); num(330, 42, "2"); num(662, 240, "3"); num(112, 470, "4")

# B: 5 host X -> x_demux -> ATTN r2 ; 6 rows ; 7 FFN r3 -> HT tail -> logits_mux -> host
arrow((XB + MINW, 36), (XB + PX - 2, 36))
arrow((XB + PX - 2 + MINW, 128), (XB + PX + 60, 128))
arrow((XB + PX + 200, 23), (XB + PX + P + 60, 23)); arrow((XB + PX + P + 60, 237), (XB + PX + 200, 237))
arrow((XB + PX + 2 * P, 237), (XB + PX + 2 * P, 257 + 22)); arrow((XB + PX + 2 * P, 257 + 22), (XB + PX + P + 200, 257 + 22))
arrow((XB + PX + P + 60, 257 + 236), (XB + PX + 200, 257 + 236))
arrow((XB + PX + 200, 257 + 22), (XB + PX + P + 60, 257 + 22))
arrow((XB + PX + 40, 257 + 236), (XB + HT_X + HT_W - 2, 257 + 236))   # FFN r3 -> HT tail
arrow((XB + HT_X + HT_W - 10, 257 + 250), (XB + HT_X + HT_W - 10, 513 + 3))   # tail -> logits_mux
arrow((XB + HT_X + 60, 516), (XB + MINW + 2, 24), rad=-0.35)           # logits_mux -> host port
num(XB + 150, 100, "5"); num(XB + 330, 42, "6"); num(XB + 112, 470, "7")

# ---------------- hosts + inter-wafer hop (measured) ----------------
hx, hw, hh = FAB_W + 60, GAP - 120, 185
for (y, name, lines) in [
    (5, "host A (pod worker, 10.27.27.225)",
     "cs_python launch.py --pp-role a\n• recv Z: SdkRuntime stream (D2H)\n• embed = W_E[token] row copy 13 µs\n• send X: stream (H2D) 5 µs"),
    (325, "host B (pod worker, 10.27.27.121)",
     "cs_python launch.py --pp-role b\n• send X: stream (H2D) 5 µs\n• recv token record: stream (D2H)\n• parse top-K + sampled id"),
]:
    ax.add_patch(FancyBboxPatch((hx, y), hw, hh, boxstyle="round,pad=6", fc=C_HOST, ec="#8a8a85", lw=0.9, zorder=2))
    label(hx + hw / 2, y + 22, name, fs=8.2, col="#1a1a19", fontweight="bold")
    label(hx + 12, y + 60, lines, fs=7.2, col="#2b2b29", ha="left", va="top")

# host A <-> wafer A edge (Z out at west lvds loc 1, X in at loc 36)
# host A <-> wafer A: routed above the wafer as polylines (Z out on y=-48, X in on y=-26)
ax.plot([4, 24, hx - 70, hx - 2], [-2, -48, -48, 40], color="#7b4fd1", lw=1.8, zorder=5, solid_capstyle="round")
arrow((hx - 30, 40 - 28), (hx - 2, 40), colour="#7b4fd1", lw=1.8)
ax.plot([hx - 2, hx - 90, 44, 6], [5 + 120, -26, -26, 2], color="#1a1a19", lw=1.6, zorder=5, solid_capstyle="round")
arrow((30, -12), (6, 3), colour="#1a1a19", lw=1.6)

# RDMA A -> B (5,120 B) and B -> A (8 B)
ax.add_patch(FancyBboxPatch((hx + 44, 234), hw - 88, 66, boxstyle="round,pad=3", fc="#e3f3ec", ec="#1baf7a", lw=1.0, zorder=3))
label(hx + hw / 2, 248, "pod-to-pod RDMA on the 10.27.x RoCE underlay", fs=7.2, col="#0f5c40", fontweight="bold")
label(hx + hw / 2, 266, "hidden state 5,120 B ↓   ·   sampled token 8 B ↑", fs=6.9, col="#0f5c40")
label(hx + hw / 2, 284, "persistent RC QP · mlx5_0 · RoCE v2 GID 5 · WRITE_WITH_IMM · busy-poll", fs=6.3, col="#0f5c40")
arrow((hx + 20, 5 + hh + 6), (hx + 20, 325 - 8), colour="#1baf7a", lw=2.2)
arrow((hx + hw - 20, 325 - 8), (hx + hw - 20, 5 + hh + 6), colour="#1baf7a", lw=1.4, ls="--")
num(hx + 20, 222, "8"); num(hx + hw - 20, 222, "9")

# measured per-token panel
py0 = 580
ax.add_patch(FancyBboxPatch((hx - 45, py0), hw + 90, 360, boxstyle="round,pad=6", fc="#fcfcfb", ec="#8a8a85", lw=0.9, zorder=2))
label(hx + hw / 2, py0 + 22, "measured per token (lockstep, RDMA hop, CS-3 2026-09-03)", fs=8.0, col="#1a1a19", fontweight="bold")
label(hx - 33, py0 + 58,
      "end-to-end          1,378.5 µs (n=2, ±0.64 %)\n"
      "A: send X → recv Z    614 µs  18 layers+demux/z_mux+H2D/D2H\n"
      "B: send X → recv rec  708 µs  18 layers+lm_head/sample+mux\n"
      "host A embed + send    19 µs\n"
      "wire + wait residual    3 µs  (RDMA RTT 11 µs; TCP 32 µs)\n"
      "\n"
      "single wafer, same cfg  1,036 µs / token\n"
      "two wafers              1.33× host-wall · 1.32× cycles\n"
      "token sequence          byte-exact over 4,096 steps\n"
      "\n"
      "A on-wafer (X in → Z out)  488 µs  ⇒ SDK H2D+D2H 114 µs\n"
      "ring alone: ≈160 µs RTT, flat 8 B..5 KB, 24 µs on-wafer\n"
      "device cyc/token  A z_mux 1,037,476 · B tail 1,037,473\n"
      "closed loop ⇒ TSC ≈ 750 MHz (not 0.85 / 1.1 GHz)",
      fs=6.9, col="#2b2b29", ha="left", va="top", family="monospace")

# side annotations (thin columns)
ax.annotate("io lvds ports (west edge)\nkv0/kv1 @ y0/18 · X in @36 · Z/logits out @1", xy=(3, 20), xytext=(-330, 40),
            fontsize=7.3, color="#4a4a47", va="center", arrowprops=dict(arrowstyle="-", color="#8a8a85", lw=0.6))
ax.annotate("x_demux (x=130): per-STEP\nhost X fan-out (wait_ready=0)", xy=(130, 120), xytext=(-330, 130),
            fontsize=7.3, color="#4a4a47", va="center", arrowprops=dict(arrowstyle="-", color="#8a8a85", lw=0.6))
ax.annotate("z_mux (x=129, new): 1×256 gather of\nthe row-1 result lanes → host stream\n+ per-frame TSC stamp",
            xy=(129, 400), xytext=(-330, 380), fontsize=7.3, color="#4a4a47", va="center",
            arrowprops=dict(arrowstyle="-", color="#8a8a85", lw=0.6))
ax.annotate("kv_inj r (x=645+r), both wafers:\nprefill KV for its own 18 layers", xy=(XB + 648, 400), xytext=(XB + 700, 470),
            fontsize=7.3, color="#4a4a47", va="center", arrowprops=dict(arrowstyle="-", color="#8a8a85", lw=0.6))
ax.annotate("logits_mux (y=513) → host B\n(emit_north=0: no HT head above)", xy=(XB + 67, 516), xytext=(XB + 60, 640),
            fontsize=7.3, color="#4a4a47", va="center", arrowprops=dict(arrowstyle="-", color="#8a8a85", lw=0.6))

ax.set_xlim(-340, XB + FAB_W + 40)
ax.set_ylim(FAB_H + 60, -118)
ax.set_aspect("equal")
ax.set_xlabel("fabric x (PE column) — wafer A left, wafer B right (each 762×1172)")
ax.set_ylabel("fabric y (PE row, north at top)")
ax.set_title("Qwen3-4B decode split across two CS-3s — device_pp_a / device_pp_b (MAX_SEQ_LEN 8192, bsz 1) and the per-token hop",
             fontsize=10.5)
ax.text(-340, -100, "flow: 1 host X→x_demux→ATTN r0 · 2 ATTN⇄FFN same-row multicast · 3 K-pipe south→r1 · 4 FFN r1→west strip→z_mux→host A (D2H) · "
        "8 RDMA 5,120 B → host B · 5 x_demux→ATTN r2 (H2D) · 6 rows r2/r3 · 7 FFN r3→HT tail→logits_mux→host B (D2H) · 9 RDMA 8 B token → host A (dashed)",
        fontsize=7.2, color="#4a4a47", va="bottom")
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
handles = [Rectangle((0, 0), 1, 1, fc=c) for c in (C_ATTN, C_FFN, C_HT, C_STRIP, C_IO, C_ZMUX, C_UNUSED)]
ax.legend(handles, ["ATTN role (KV host)", "FFN role", "HT tail", "strip columns (K-pipe relay)",
                    "KV injector / demux / mux / io", "z_mux (new Z egress column)", "unplaced fabric"],
          loc="lower left", bbox_to_anchor=(0.0, -0.10), ncol=4, frameon=False, fontsize=8)
ax.text(-340, FAB_H + 8, "Geometry: launch.py placement constants for PP_ROLE a/b + sim_port_map.json lvds ports (west edge); "
        "1–3-PE-wide columns widened for visibility. Per-PE SRAM = single-wafer role images (same ELFs). Fabric 762×1172 from the 2026-06-28 device study.",
        fontsize=7, color="#4a4a47", va="top")
fig.tight_layout()
out = os.path.join(HERE, "..", "cs3", "two_wafer_pp_floorplan.png")
fig.savefig(out, bbox_inches="tight")
print("wrote", os.path.abspath(out))
