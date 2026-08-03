#!/usr/bin/env python3
"""Generate the conceptual floor-map schedule used by the force-decode note."""

from pathlib import Path
from xml.sax.saxutils import escape


OUT = Path(__file__).parent / "figures" / "force-vs-free-decode-floor-map.svg"
W, H = 1900, 1120


def text(x, y, value, size=18, weight=400, fill="#172033", anchor="start"):
    return (
        f'<text x="{x}" y="{y}" font-family="Inter,Arial,sans-serif" '
        f'font-size="{size}" font-weight="{weight}" fill="{fill}" '
        f'text-anchor="{anchor}">{escape(value)}</text>'
    )


def rect(x, y, w, h, fill, stroke="#cad3df", rx=10, sw=2):
    return (
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>'
    )


def line(x1, y1, x2, y2, stroke="#8995a8", sw=3, dash=None, marker=None):
    attrs = ""
    if dash:
        attrs += f' stroke-dasharray="{dash}"'
    if marker:
        attrs += f' marker-end="url(#{marker})"'
    return (
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
        f'stroke="{stroke}" stroke-width="{sw}"{attrs}/>'
    )


# Physical stage placement for the 2 x 4 snake.
STAGE_AT = {(0, 0): 1, (1, 0): 2, (1, 1): 3, (0, 1): 4,
            (0, 2): 5, (1, 2): 6, (1, 3): 7, (0, 3): 8}


def panel(parts, x, y, tau, active, mode, note):
    """active maps stage number to token number."""
    pw, ph = 344, 378
    parts.append(rect(x, y, pw, ph, "#ffffff", "#d9e0ea", 16, 2))
    parts.append(text(x + 18, y + 31, f"τ = {tau}", 20, 700, "#172033"))
    parts.append(text(x + pw - 18, y + 31, note, 14, 600, "#657188", "end"))

    mx, my = x + 77, y + 70
    cw, ch, gx, gy = 92, 50, 13, 12

    # HT head and tail are intentionally outside the compute-block floor map.
    parts.append(rect(mx - 1, my - 43, 198, 29, "#e6f0ff", "#4c75dd", 7, 1.5))
    parts.append(text(mx + 98, my - 22, "HT head · embed / inject", 12, 700, "#2451bb", "middle"))

    centers = {}
    for (col, row), stage in STAGE_AT.items():
        cx, cy = mx + col * (cw + gx), my + row * (ch + gy)
        centers[stage] = (cx + cw / 2, cy + ch / 2)
        token = active.get(stage)
        if token is None:
            fill, stroke, label, sub = "#f3f5f8", "#c9d1dc", f"S{stage}", "idle"
            main_color, sub_color = "#647087", "#9aa4b4"
        else:
            fill = "#ece5ff" if mode == "free" else "#dff7ee"
            stroke = "#7747e8" if mode == "free" else "#13876b"
            label, sub = f"S{stage}", f"T{token}"
            main_color, sub_color = "#35205f" if mode == "free" else "#0b5e4b", stroke
        parts.append(rect(cx, cy, cw, ch, fill, stroke, 8, 2))
        parts.append(text(cx + 12, cy + 21, label, 14, 700, main_color))
        parts.append(text(cx + cw - 12, cy + 34, sub, 16 if token else 12, 800 if token else 500,
                          sub_color, "end"))

    # Snake route: S1 -> ... -> S8.
    for s in range(1, 8):
        a, b = centers[s], centers[s + 1]
        parts.append(line(a[0], a[1], b[0], b[1], "#a9b2c1", 2, None, "arrow-gray"))

    tx, ty = mx - 1, my + 4 * (ch + gy) + 1
    parts.append(rect(tx, ty, 198, 29, "#fff0e3", "#d97724", 7, 1.5))
    parts.append(text(tx + 99, ty + 20, "HT tail · logits / sample", 12, 700, "#a85011", "middle"))
    parts.append(line(centers[8][0], centers[8][1] + ch / 2, tx + 99, ty, "#d97724", 2, None, "arrow-orange"))

    if mode == "free":
        # Feedback dependence from the sampled output back to the injector.
        fx = x + pw - 23
        parts.append(f'<path d="M {tx + 198} {ty + 15} H {fx} V {my - 29} H {mx + 198}" '
                     'fill="none" stroke="#7747e8" stroke-width="3" stroke-dasharray="7 5" '
                     'marker-end="url(#arrow-purple)"/>')
    else:
        parts.append(text(x + pw / 2, y + ph - 18, "Known next token: no sampling dependency", 13, 700,
                          "#13876b", "middle"))


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
        '<defs>',
        '<marker id="arrow-gray" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0,0 L7,3.5 L0,7 Z" fill="#a9b2c1"/></marker>',
        '<marker id="arrow-orange" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0,0 L7,3.5 L0,7 Z" fill="#d97724"/></marker>',
        '<marker id="arrow-purple" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0,0 L7,3.5 L0,7 Z" fill="#7747e8"/></marker>',
        '</defs>',
        rect(0, 0, W, H, "#f7f9fc", "#f7f9fc", 0, 0),
        text(54, 58, "Free decode vs. force decode on the 2×4 on-wafer pipeline", 32, 800, "#121a2b"),
        text(54, 91, "Conceptual schedule; each τ is one normalized block service interval, not a cycle-accurate equal-duration stage.", 17, 400, "#687489"),
        text(54, 137, "ORDINARY / FREE DECODE", 19, 800, "#6532d6"),
        text(340, 137, "The next input token is unknown until S8 → logits → sampling → HT head completes.", 16, 500, "#4c5668"),
        text(54, 596, "FORCE DECODE (TEACHER FORCING)", 19, 800, "#08745b"),
        text(420, 596, "The next input token is already known, so stages can hold different tokens concurrently.", 16, 500, "#4c5668"),
    ]

    xs = [54, 422, 790, 1158, 1526]
    taus = [0, 1, 2, 7, 8]
    free = [
        {1: 1}, {2: 1}, {3: 1}, {8: 1}, {1: 2},
    ]
    forced = [
        {1: 1},
        {2: 1, 1: 2},
        {3: 1, 2: 2, 1: 3},
        {8: 1, 7: 2, 6: 3, 5: 4, 4: 5, 3: 6, 2: 7, 1: 8},
        {8: 2, 7: 3, 6: 4, 5: 5, 4: 6, 3: 7, 2: 8, 1: 9},
    ]
    free_notes = ["inject T1", "advance", "advance", "sample", "inject T2"]
    force_notes = ["inject T1", "inject T2", "inject T3", "pipeline full", "steady state"]

    for x, tau, active, note in zip(xs, taus, free, free_notes):
        panel(parts, x, 156, tau, active, "free", note)
    for x, tau, active, note in zip(xs, taus, forced, force_notes):
        panel(parts, x, 615, tau, active, "force", note)

    parts.extend([
        rect(54, 1014, 1792, 72, "#ffffff", "#d9e0ea", 12, 1.5),
        rect(82, 1034, 27, 27, "#ece5ff", "#7747e8", 5, 2),
        text(120, 1054, "free-decode active block", 14, 600, "#4c5668"),
        rect(348, 1034, 27, 27, "#dff7ee", "#13876b", 5, 2),
        text(386, 1054, "force-decode active block", 14, 600, "#4c5668"),
        text(668, 1054, "Tn = token n", 14, 600, "#4c5668"),
        text(815, 1054, "Sn = spatial pipeline stage n", 14, 600, "#4c5668"),
        text(1115, 1054, "Physical snake: S1→S2→S3→…→S8", 14, 600, "#4c5668"),
        text(1488, 1054, "Same transformer math; different launch dependency", 14, 700, "#172033"),
        '</svg>',
    ])
    OUT.write_text("\n".join(parts), encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    main()
