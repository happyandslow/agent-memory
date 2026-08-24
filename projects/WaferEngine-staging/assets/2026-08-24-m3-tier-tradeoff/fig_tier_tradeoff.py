#!/usr/bin/env python3
"""Three-tier KV resume tradeoff: recompute vs host reload vs on-chip strip.

Extends the M2 E10/E10D boundary figure (A recompute vs B host-reload,
crossing H*=744) with the M3-measured on-chip tier C. Same setting as the
deck figure: starting prefix S=256, L_new=256, delta reload; resume span =
time to be ready to continue decoding after recovering H tokens of history.

Sources (all real WSE-3):
- A: E10D direct measurements (768 tok -> 57.32 ms, 1280 -> 96.96 ms),
  slope 77.4 us/token (E9 f_forced ~112-130 us/tok at larger L).
- B: E5/E10 kv_ingress I(H) anchors (46.1..338.27 ms, 256..8192 tok)
  + measured delta 19.05-20.17 ms; direct E10D points 65.29 / 76.31 ms.
- C: M3 column_cycle_demo_multirow_v5 R=1 dsd device cells (2026-08-23
  matrix, 0-cycle spread): reload share = full - park_span =
  219,773 cyc @E=64 (H=1024), 1,710,717 cyc @E=512 (H=8192) = 13.0
  cyc/word; E = 16*ceil(H/256) words/PE, per-block columns in parallel,
  0.85 GHz. Multi-row adds tax_v4 = 1.29 cyc/word (negligible; v4 design).
"""
import math

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

CLOCK_GHZ = 0.85
DELTA_MS = 19.6          # measured L_new=256 forced-decode delta (E10D: 19.05/20.17)

# ---- A: recompute (force-decode S -> H+L_new), two-point measured line
A_PTS = {512: 57.32, 1024: 96.96}       # H -> ms (measured, E10D)
_slope = (96.96 - 57.32) / (1280 - 768)  # per total token
_icpt = 57.32 - _slope * 768
def lane_a(h): return _icpt + _slope * (h + 256)

# ---- B: host reload I(H) + delta
I_H = {256: 46.1, 512: 46.24, 1024: 56.14, 2048: 85.69, 4096: 169.89, 8192: 338.27}
B_DIRECT = {512: 65.29, 1024: 76.31}    # fully measured E10D cells
def lane_b(h):
    ks = sorted(I_H)
    if h <= ks[0]: i = I_H[ks[0]]
    elif h >= ks[-1]: i = I_H[ks[-1]]
    else:
        for a, b in zip(ks, ks[1:]):
            if a <= h <= b:
                t = (h - a) / (b - a)
                i = I_H[a] * (1 - t) + I_H[b] * t
                break
    return i + DELTA_MS

# ---- C: on-chip strip reload (v5 R=1 dsd measured share) + delta
# reload cycles = 6,781 + 3,328*E  (through the two measured cells)
def onchip_reload_ms(h):
    e = 16 * math.ceil(h / 256)
    return (6781 + 3328 * e) / CLOCK_GHZ / 1e6  # cyc -> ms
def lane_c(h): return onchip_reload_ms(h) + DELTA_MS
C_MEASURED = {1024: 219773 / CLOCK_GHZ / 1e6, 8192: 1710717 / CLOCK_GHZ / 1e6}  # ms

HS = [256 * k for k in range(1, 33)]
PURPLE, BLUE, GREEN = "#7048e8", "#1a56db", "#2f9e44"

fig, ax = plt.subplots(figsize=(12.6, 6.6))
ax.set_facecolor("#fafafa")
ax.plot(HS, [lane_a(h) for h in HS], color=PURPLE, lw=3.2,
        label="A · recompute  =  D(S, H+L$_{new}$)   (77.4 µs/tok, measured)")
ax.plot(HS, [lane_b(h) for h in HS], color=BLUE, lw=3.2,
        label="B · host reload  =  I(H) + Δ   (E5 ingress, measured)")
ax.plot(HS, [lane_c(h) for h in HS], color=GREEN, lw=3.6,
        label="C · on-chip strip  =  reload$_{strip}$(H) + Δ   (M3 device-fit)")
ax.plot(HS, [onchip_reload_ms(h) for h in HS], color=GREEN, lw=1.6, ls="--",
        alpha=0.75, label="    on-chip reload component alone (13.0 cyc/word)")

ax.scatter(list(A_PTS), list(A_PTS.values()), color=PURPLE, s=70, zorder=5)
ax.scatter(list(B_DIRECT), list(B_DIRECT.values()), color=BLUE, s=70, zorder=5)
ax.scatter(list(C_MEASURED), [v + DELTA_MS for v in C_MEASURED.values()],
           color=GREEN, s=90, marker="s", zorder=5)
ax.scatter(list(C_MEASURED), list(C_MEASURED.values()),
           color=GREEN, s=70, marker="s", facecolors="none", zorder=5)

ax.axvline(744, color="k", ls=":", lw=1.6)
ax.annotate("old A×B crossing\nH* = 744 (E10)", xy=(744, 180), ha="center",
            fontsize=11, fontweight="bold")
ax.annotate("C ≈ Δ floor: on-chip reload adds only 0.06–2.0 ms\n"
            "→ beats A for any parked history; 46–170× below B's I(H)",
            xy=(2900, 22.5), xytext=(700, 3.6), fontsize=11.5, color=GREEN,
            fontweight="bold",
            arrowprops=dict(arrowstyle="->", color=GREEN, lw=1.6))

ax.set_xscale("log", base=2)
ax.set_yscale("log")
ax.set_xticks([256, 512, 1024, 2048, 4096, 8192])
ax.set_xticklabels(["256", "512", "1,024", "2,048", "4,096", "8,192"], fontsize=12)
ax.set_yticks([0.1, 0.3, 1, 3, 10, 30, 100, 300])
ax.set_yticklabels(["0.1", "0.3", "1", "3", "10", "30", "100", "300"], fontsize=12)
ax.set_xlim(256, 8192)
ax.set_ylim(0.05, 420)
ax.set_xlabel("History to recover H (tokens)", fontsize=14)
ax.set_ylabel("Projected resume span (ms)", fontsize=14)
ax.set_title("KV resume: the on-chip tier sits under both old options",
             fontsize=19, fontweight="bold", loc="left", pad=30)
ax.text(0, 1.03, "Setting: S=256, L$_{new}$=256, delta reload · dots/squares = device-measured · "
        "C: v5 single-row dsd, per-block columns parallel; multi-row adds ≤1.3 cyc/word (v4)",
        transform=ax.transAxes, fontsize=10.5, color="#666666")
ax.grid(True, which="both", color="#e0e0e0", lw=0.7)
ax.legend(fontsize=11.5, loc="lower right", framealpha=0.95)
for s in ("top", "right"):
    ax.spines[s].set_visible(False)

out = __file__.rsplit("/", 1)[0]
fig.tight_layout()
fig.savefig(f"{out}/tier_tradeoff.png", dpi=170)
fig.savefig(f"{out}/tier_tradeoff.svg")
print("A(8192) =", round(lane_a(8192), 1), "B(8192) =", round(lane_b(8192), 1),
      "C(8192) =", round(lane_c(8192), 2), "reload-only(8192) =",
      round(onchip_reload_ms(8192), 3))
