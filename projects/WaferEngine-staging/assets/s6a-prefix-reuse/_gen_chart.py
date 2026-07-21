#!/usr/bin/env python3
"""Prefill prefix-reuse device results — 3-panel chart.

Palette: dataviz categorical slots 1 (blue) + 2 (green); validated PASS on all
six checks against the #f7f9fb surface used by the other agent-memory assets.
tritan CVD dE 7.6 sits in the floor band, so BOTH series are direct-labelled
(secondary encoding), not distinguished by colour alone.
"""
import os

OUT = "/home/lexu/agent-memory/projects/WaferEngine-staging/assets/s6a-prefix-reuse"
os.makedirs(OUT, exist_ok=True)

F = "ui-sans-serif,Segoe UI,Helvetica,Arial"
SURF = "#f7f9fb"
INK, MUTE, FAINT = "#0d1b26", "#4a5b66", "#8a97a0"
GRID = "#dce4ea"
S1, S2 = "#2a78d6", "#008300"          # L=8192, L=16384

CLK = 1100.0                            # cycles per microsecond (1.1 GHz)

# span_cycles, measured on 524,288 PEs. k = chunks of prefix reused.
RUNS = {
    8192:  {"n": 32, "color": S1, "pts": [(0, 1101615635), (8, 1016462831),
                                          (16, 850635411), (24, 604117559)]},
    16384: {"n": 64, "color": S2, "pts": [(0, 3459432815), (16, 3208533364),
                                          (32, 2634720942), (48, 1738254665)]},
}
MISSING = None                          # complete 2026-07-21; k48 measured

for L, r in RUNS.items():
    base = r["pts"][0][1]
    r["rows"] = [{"reuse": 100.0 * k / r["n"],
                  "ms": span / CLK / 1000.0,
                  "tput": L / (span / CLK / 1e6),
                  "saving": 100.0 * (1 - span / base)} for k, span in r["pts"]]

W, H = 1580, 700
PW, PH = 400, 345                       # plot area
PY = 190                                # plot top
PXS = [96, 596, 1096]                   # plot lefts

out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
       f'viewBox="0 0 {W} {H}" font-family="{F}">',
       f'<rect width="{W}" height="{H}" fill="{SURF}"/>']


def T(x, y, s, size=13, fill=INK, w="500", anchor="start"):
    out.append(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{w}" '
               f'fill="{fill}" text-anchor="{anchor}">{s}</text>')


T(50, 42, "Prefill prefix reuse on WSE-3 — measured device results", 22, INK, "700")
T(50, 68, "524,288 PEs (Pw 512 x Ph 1024), 28 layers, dim 2048, vocab 151,936. "
          "Pure on-device single-request latency: host stream preparation and logit "
          "post-processing are outside the timed window.", 13, MUTE)
T(50, 88, "n = 1 run per point, no repeats — variance uncharacterised. Every reuse "
          "point verified BYTE-IDENTICAL to its cold round.", 13, MUTE)

# legend — always present for >=2 series
lx = 50
for L, r in RUNS.items():
    out.append(f'<line x1="{lx}" y1="112" x2="{lx+26}" y2="112" stroke="{r["color"]}" stroke-width="2"/>')
    out.append(f'<circle cx="{lx+13}" cy="112" r="4.5" fill="{r["color"]}" stroke="{SURF}" stroke-width="2"/>')
    T(lx + 34, 116, f"prompt = {L:,} tokens ({r['n']} chunks)", 13, INK, "600")
    lx += 250


def panel(px, title, sub, key, ymax, fmt, ticks, note=None):
    out.append(f'<line x1="{px}" y1="{PY}" x2="{px}" y2="{PY+PH}" stroke="{GRID}" stroke-width="1.2"/>')
    out.append(f'<line x1="{px}" y1="{PY+PH}" x2="{px+PW}" y2="{PY+PH}" stroke="{GRID}" stroke-width="1.2"/>')
    T(px, PY - 34, title, 16, INK, "700")
    T(px, PY - 15, sub, 12, MUTE)

    for t in ticks:                                     # recessive gridlines
        y = PY + PH - (t / ymax) * PH
        if t:
            out.append(f'<line x1="{px}" y1="{y:.1f}" x2="{px+PW}" y2="{y:.1f}" '
                       f'stroke="{GRID}" stroke-width="1" stroke-dasharray="3 4"/>')
        T(px - 10, y + 4, fmt(t), 11, FAINT, "500", "end")

    for xr in (0, 25, 50, 75):                          # x axis = reuse fraction
        x = px + (xr / 75.0) * PW
        T(x, PY + PH + 22, f"{xr}%", 12, MUTE, "500", "middle")
    T(px + PW / 2, PY + PH + 44, "share of the prompt reused", 12.5, MUTE, "600", "middle")

    for L, r in RUNS.items():
        pts = [(px + (d["reuse"] / 75.0) * PW, PY + PH - (d[key] / ymax) * PH) for d in r["rows"]]
        out.append('<polyline points="' + " ".join(f"{x:.1f},{y:.1f}" for x, y in pts) +
                   f'" fill="none" stroke="{r["color"]}" stroke-width="2"/>')
        for x, y in pts:
            out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{r["color"]}" '
                       f'stroke="{SURF}" stroke-width="2"/>')
        # direct label on the last point (secondary encoding; not every point)
        d = r["rows"][-1]
        # both series now reach 75%; nudge the upper series' label up, lower down,
        # so the two end labels (near-coincident on the saving panel) don't collide
        dy = -12 if L == 16384 else 15
        out.append(f'<text x="{pts[-1][0]+11:.1f}" y="{pts[-1][1]+dy:.1f}" font-size="12.5" '
                   f'font-weight="700" fill="{INK}">{fmt(d[key])}</text>')
    if note:
        T(px, PY + PH + 74, note, 12, MUTE)


panel(PXS[0], "Latency per request", "milliseconds, lower is better", "ms",
      3300, lambda v: f"{v:,.0f} ms" if v else "0", [0, 1000, 2000, 3000])
panel(PXS[1], "Throughput per request", "tokens/s, higher is better", "tput",
      16000, lambda v: f"{v:,.0f}" if v else "0", [0, 4000, 8000, 12000, 16000])
panel(PXS[2], "Time saved vs no reuse", "percent of the cold-run latency", "saving",
      50, lambda v: f"{v:.1f}%" if v else "0%", [0, 10, 20, 30, 40, 50])

# the finding, stated on the panel that shows it
out.append(f'<rect x="{PXS[2]}" y="{PY+PH+64}" width="{PW+60}" height="90" rx="6" '
           f'fill="#eef4fa" stroke="#245f96" stroke-width="1.4"/>')
T(PXS[2] + 14, PY + PH + 85, "Fraction sets the saving; length is a second-order effect.", 13, "#12356a", "700")
T(PXS[2] + 14, PY + PH + 103, "Saving  L=8192 vs 16384:  25% -> 7.7/7.3,  50% -> 22.8/23.8,", 12.5, MUTE)
T(PXS[2] + 14, PY + PH + 120, "75% -> 45.2/49.8.  The gap grows with reuse and favours", 12.5, MUTE)
T(PXS[2] + 14, PY + PH + 137, "the LONGER prompt — its skipped chunks are the pricier ones.", 12.5, MUTE)

T(PXS[0], PY + PH + 78, "Reuse is strongly sub-linear: half the prompt cached", 12.5, MUTE)
T(PXS[0], PY + PH + 95, "buys well under a quarter of the time. A chunk's cost", 12.5, MUTE)
T(PXS[0], PY + PH + 112, "grows with the text before it, so the reused prefix is", 12.5, MUTE)
T(PXS[0], PY + PH + 129, "always the cheapest part of the request.", 12.5, MUTE)

T(PXS[1], PY + PH + 78, "Both prompt lengths now measured at all four reuse", 12.5, MUTE)
T(PXS[1], PY + PH + 95, "fractions (0 / 25 / 50 / 75%), 524,288 PEs, n=1 each.", 12.5, MUTE)
T(PXS[1], PY + PH + 112, "Decode side (not shown): retain saves -49.3% at", 12.5, MUTE)
T(PXS[1], PY + PH + 129, "MAX_SEQ 4096, -34.6% at 1024 — set by the redo pattern.", 12.5, MUTE)

out.append('</svg>')
p = os.path.join(OUT, "prefill-prefix-reuse-latency-throughput.svg")
open(p, "w").write("\n".join(out))
os.system(f'inkscape "{p}" --export-type=png --export-dpi=144 '
          f'--export-filename="{p[:-4]}.png" 2>/dev/null')
print("wrote", p)
for L, r in RUNS.items():
    for d in r["rows"]:
        print(f"  L={L:6d}  reuse {d['reuse']:5.1f}%  {d['ms']:8.2f} ms  "
              f"{d['tput']:9.1f} tok/s  saving {d['saving']:5.2f}%")
