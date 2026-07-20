#!/usr/bin/env python3
"""Figures for the 2-slide KV-transfer deck (kv-transfer_build.py consumes these).

Two jobs:
  1. Crop the committed topology diagrams so their clipped bottom caption strip is
     dropped — the slide carries a clean caption in real text instead.
  2. Draw the device bandwidth-ladder chart as SVG -> PNG.

Chart design follows the dataviz skill: one measured series, so ONE color
(#2a78d6, validated >= 3:1 on a white slide surface, all checks PASS). Growth is
already encoded by bar height, so shading the bars too would be redundant
encoding. Reference lines are chrome (muted ink), not series colors.
"""
import os
import cairosvg
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(os.path.dirname(HERE), "assets", "prefill-decode-transfer")

# ---------------------------------------------------------------- 1. crop diagrams
# (left, upper, right, lower) — cut the caption band that renders clipped in the PNG.
for src, dst, box in (
        ("kv-topo-block.png",   "fig_topo_block.png",   (0, 0, 838, 800)),
        ("kv-topo-regions.png", "fig_topo_regions.png", (0, 0, 875, 752))):
    im = Image.open(os.path.join(ASSETS, src)).crop(box)
    im.save(os.path.join(HERE, dst))
    print("cropped", dst, im.size)

# ------------------------------------------------------------------- 2. bw ladder
# Device TSC numbers, ContextBase log 2026-07-17 (all real silicon, no sim).
RUNGS = [  # label, Pw, P_BLOCK, KV volume, A+B us, effective GB/s
    ("L0", "16",  "8",   "16 KiB",  340,  0.048),
    ("L1", "32",  "16",  "32 KiB",  604,  0.054),
    ("L2", "64",  "32",  "256 KiB", 1208, 0.217),
    ("L3", "128", "64",  "1 MiB",   2344, 0.447),
    ("L4", "256", "128", "4 MiB",   4639, 0.904),
    ("L5", "512", "256", "16 MiB",  9304, 1.803),
]
LINK_DEVICE = 3.909   # one fabric link, clean single-@mov32 stream, measured on device
LINK_SPEC = 4.4       # Cerebras disclosed per-link (32-bit bidirectional @ 1.1 GHz)

SERIES = "#2a78d6"      # validated single-series blue
INK = "#0b0b0b"         # primary
INK2 = "#52514e"        # secondary
MUTED = "#898781"       # axis / reference-line chrome
GRID = "#e1e0d9"
FONT = 'system-ui,-apple-system,"Segoe UI",Helvetica,Arial,sans-serif'

W, H = 1560, 660
L, R, T, B = 96, 40, 66, 108           # plot margins
PW, PH = W - L - R, H - T - B
YMAX = 4.8
def y(v): return T + PH * (1 - v / YMAX)

s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
     f'viewBox="0 0 {W} {H}" font-family=\'{FONT}\'>',
     f'<rect width="{W}" height="{H}" fill="#ffffff"/>']

# y grid + ticks
for gv in [0, 1, 2, 3, 4]:
    gy = y(gv)
    s.append(f'<line x1="{L}" y1="{gy:.1f}" x2="{L+PW}" y2="{gy:.1f}" '
             f'stroke="{GRID}" stroke-width="1"/>')
    s.append(f'<text x="{L-14}" y="{gy+5:.1f}" text-anchor="end" font-size="20" '
             f'fill="{MUTED}">{gv}</text>')
s.append(f'<text x="{L-14}" y="{T-26}" text-anchor="end" font-size="20" fill="{INK2}">GB/s</text>')

# bars
n = len(RUNGS)
slot = PW / n
bw = slot * 0.46
for i, (lab, pw_, blk, vol, ab, gbs) in enumerate(RUNGS):
    cx = L + slot * (i + 0.5)
    bx, by_ = cx - bw / 2, y(gbs)
    bh = y(0) - by_
    # 4px rounded data-end anchored to the baseline
    s.append(f'<path d="M{bx:.1f},{y(0):.1f} L{bx:.1f},{by_+4:.1f} '
             f'Q{bx:.1f},{by_:.1f} {bx+4:.1f},{by_:.1f} '
             f'L{bx+bw-4:.1f},{by_:.1f} Q{bx+bw:.1f},{by_:.1f} {bx+bw:.1f},{by_+4:.1f} '
             f'L{bx+bw:.1f},{y(0):.1f} Z" fill="{SERIES}"/>')
    # direct value label
    s.append(f'<text x="{cx:.1f}" y="{by_-12:.1f}" text-anchor="middle" font-size="23" '
             f'font-weight="700" fill="{INK}">{gbs:.3f}</text>')
    # x labels: rung, geometry, volume+time
    s.append(f'<text x="{cx:.1f}" y="{y(0)+30:.1f}" text-anchor="middle" font-size="23" '
             f'font-weight="700" fill="{INK}">{lab}</text>')
    s.append(f'<text x="{cx:.1f}" y="{y(0)+54:.1f}" text-anchor="middle" font-size="18" '
             f'fill="{INK2}">Pw {pw_} · blk {blk}</text>')
    s.append(f'<text x="{cx:.1f}" y="{y(0)+76:.1f}" text-anchor="middle" font-size="18" '
             f'fill="{MUTED}">{vol} in {ab/1000:.1f} ms</text>')

# baseline
s.append(f'<line x1="{L}" y1="{y(0):.1f}" x2="{L+PW}" y2="{y(0):.1f}" '
         f'stroke="#c3c2b7" stroke-width="1.5"/>')

# reference lines (chrome, not series colors)
for val, txt, dash in ((LINK_SPEC, f'spec ~{LINK_SPEC} GB/s per link', "2 6"),
                       (LINK_DEVICE, f'one fabric link, clean stream — measured {LINK_DEVICE:.2f} GB/s', "8 5")):
    ly = y(val)
    s.append(f'<line x1="{L}" y1="{ly:.1f}" x2="{L+PW}" y2="{ly:.1f}" stroke="{MUTED}" '
             f'stroke-width="2" stroke-dasharray="{dash}"/>')
    s.append(f'<text x="{L+PW-6}" y="{ly-10:.1f}" text-anchor="end" font-size="19" '
             f'fill="{INK2}">{txt}</text>')

# the gap annotation
# anchored on the L5 bar's centre so the lower end lands ON the bar top, not in space
gy0, gy1 = y(LINK_DEVICE), y(1.803)
ax = L + (PW / len(RUNGS)) * (len(RUNGS) - 0.5)
s.append(f'<line x1="{ax:.1f}" y1="{gy0:.1f}" x2="{ax:.1f}" y2="{gy1:.1f}" stroke="{INK2}" '
         f'stroke-width="2" marker-start="url(#a)" marker-end="url(#a)"/>')
s.append('<defs><marker id="a" markerWidth="9" markerHeight="9" refX="4.5" refY="4.5" '
         f'orient="auto"><circle cx="4.5" cy="4.5" r="3" fill="{INK2}"/></marker></defs>')
s.append(f'<text x="{ax-16:.1f}" y="{(gy0+gy1)/2-4:.1f}" text-anchor="end" font-size="20" '
         f'font-weight="700" fill="{INK}">2.2x below</text>')
s.append(f'<text x="{ax-16:.1f}" y="{(gy0+gy1)/2+20:.1f}" text-anchor="end" font-size="18" '
         f'fill="{INK2}">a single clean link</text>')

s.append('</svg>')

svg_path = os.path.join(HERE, "fig_bw_ladder.svg")
png_path = os.path.join(HERE, "fig_bw_ladder.png")
open(svg_path, "w").write("\n".join(s))
cairosvg.svg2png(url=svg_path, write_to=png_path, output_width=W * 2, output_height=H * 2)
print("wrote", png_path, Image.open(png_path).size)
