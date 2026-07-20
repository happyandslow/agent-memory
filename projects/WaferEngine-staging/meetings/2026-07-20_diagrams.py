#!/usr/bin/env python3
"""Two mechanism diagrams for the weekly deck.

Palette + typography copied from the existing floorplan assets
(agent-memory .../assets/color-audit/prefill_floorplan.svg) so the slides read
as part of the same family.
"""
import os

OUT = os.path.dirname(os.path.abspath(__file__))
F = "ui-sans-serif,Segoe UI,Helvetica,Arial"
INK, MUTE = "#0d1b26", "#4a5b66"
ORANGE, ORANGE_D = "#e8b06a", "#a86a1e"       # work actually computed
GREEN, GREEN_D = "#84c98a", "#155024"         # resident / kept, no work
BLUE, BLUE_D = "#6aa9e0", "#2c6fb0"           # host traffic
RED = "#c0392b"                               # wasted / discarded
GREY, GREY_D = "#c2c2c2", "#6a7883"

W, H, SHIFT = 1706, 690, 60


def txt(x, y, s, size=15, fill=INK, weight="500", anchor="start"):
    return (f'<text x="{x}" y="{y}" font-size="{size}" font-family="{F}" '
            f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}">{s}</text>')


def box(x, y, w, h, fill, stroke, op=1.0, rx=3, dash=""):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" '
            f'fill-opacity="{op}" stroke="{stroke}" stroke-width="1.5"{d}/>')


HEAD = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
        '<defs>'
        f'<marker id="a" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" '
        f'orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" fill="{BLUE_D}"/></marker>'
        f'<marker id="ar" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" '
        f'orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" fill="{RED}"/></marker>'
        '</defs>'
        f'<g transform="translate(0,-{SHIFT})">')


# ───────────────────────────────────────────────────────── prefill
def prefill():
    s = [HEAD]
    N, CW, GAP, X0 = 12, 96, 6, 470
    K = 6                                     # reused prefix = half
    row_w = N * (CW + GAP) - GAP

    def row(y, label, sub, kept, host_from):
        o = []
        o.append(txt(40, y + 34, label, 19, INK, "700"))
        o.append(txt(40, y + 58, sub, 14, MUTE))
        # host stream bar
        hx = X0 + host_from * (CW + GAP)
        hw = row_w - (hx - X0)
        o.append(box(hx, y - 34, hw, 22, BLUE, BLUE_D, 0.55))
        o.append(txt(hx + hw / 2, y - 19, "tokens streamed from host", 17, BLUE_D, "600", "middle"))
        for i in range(N):
            x = X0 + i * (CW + GAP)
            o.append(f'<path d="M{x + CW/2} {y-12} L{x + CW/2} {y+2}" stroke="{BLUE_D}" '
                     f'stroke-width="1.2" marker-end="url(#a)"/>' if i >= host_from else '')
            if i < kept:
                o.append(box(x, y + 8, CW, 62, GREEN, GREEN_D, 0.75))
                o.append(txt(x + CW / 2, y + 36, "kept", 23, GREEN_D, "700", "middle"))
                o.append(txt(x + CW / 2, y + 54, "no work", 23, GREEN_D, "500", "middle"))
            else:
                o.append(box(x, y + 8, CW, 62, ORANGE, ORANGE_D, 0.85))
                o.append(txt(x + CW / 2, y + 43, "compute", 23, ORANGE_D, "700", "middle"))
            o.append(txt(x + CW / 2, y + 88, str(i), 14, MUTE, "500", "middle"))
        return o

    s.append(txt(X0, 104, "K/V cache banks, one row per PE   →   one cell = one CHUNK_SIZE chunk "
                          "(32 of them at 8,192 tokens)", 23, MUTE))

    s += row(200, "Cold request", "start_chunk = 0", 0, 0)
    s += row(440, "Warm request", f"start_chunk = {K}", K, K)

    # the boundary callout
    bx = X0 + K * (CW + GAP)
    s.append(f'<path d="M{bx} {420} L{bx} {575}" stroke="{RED}" stroke-width="2" '
             f'stroke-dasharray="5 4"/>')
    s.append(txt(bx + 10, 571, "start_chunk", 23, RED, "700"))

    s.append(txt(40, 636, "enter_request used to hard-set  current_chunk = 0 ;  it now sets  "
                          "current_chunk = k.", 23, RED, "700"))
    s.append(txt(40, 668, "The banks were never cleared — the per-request reset only rewound a "
                          "counter, so the previous request's chunks were already sitting in "
                          "SRAM. Nothing moves and there is no", 17, MUTE))
    s.append(txt(40, 692, "inverse transform, which is what makes the reuse nearly free. The one "
                          "constraint: the shared prefix has to be chunk-aligned, otherwise the "
                          "boundary chunk must be recomputed.", 17, MUTE))

    s.append('</g></svg>')
    return "\n".join(x for x in s if x)


# ────────────────────────────────────────────────────────── decode
def decode():
    s = [HEAD]
    X0, PX = 430, 1.30                        # x origin, px per token
    SEG = 256

    def seg(x, w, y, h, fill, stroke, op, t1, t2=None, tc=None):
        o = [box(x, y, w, h, fill, stroke, op)]
        o.append(txt(x + w / 2, y + h / 2 + (0 if t2 else 6), t1, 17, tc or stroke, "700", "middle"))
        if t2:
            o.append(txt(x + w / 2, y + h / 2 + 22, t2, 14, tc or stroke, "500", "middle"))
        return o

    s.append(txt(X0, 104, "Round 1 of a two-round request. Both arms must finish in the same place: "
                          "768 tokens of context.", 23, MUTE))

    for i, tok in enumerate((0, 256, 512, 768)):
        x = X0 + tok * PX
        s.append(f'<path d="M{x} 130 L{x} 552" stroke="#dce4ea" stroke-width="1"/>')
        s.append(txt(x, 578, str(tok), 14, MUTE, "500", "middle"))
    s.append(txt(X0 + 384 * PX, 602, "context position", 17, MUTE, "500", "middle"))

    # ── no-reuse
    y = 175
    s.append(txt(40, y + 30, "Without reuse", 23, INK, "700"))
    s.append(txt(40, y + 54, "KV discarded at the", 17, MUTE))
    s.append(txt(40, y + 74, "round boundary", 17, MUTE))
    s += seg(X0, SEG * PX, y, 112, GREY, GREY_D, 0.55, "re-prefilled", "(not timed)")
    s += seg(X0 + SEG * PX, SEG * PX, y, 112, RED, RED, 0.30, "256 steps DECODED AGAIN",
             "pure waste", RED)
    s += seg(X0 + 2 * SEG * PX, SEG * PX, y, 112, ORANGE, ORANGE_D, 0.85, "256 new steps")
    s.append(txt(X0 + 3 * SEG * PX + 30, y + 32, "512 decode steps", 23, INK, "700"))
    s.append(txt(X0 + 3 * SEG * PX + 30, y + 54, "262.9 M cycles", 18, MUTE, "500"))

    # ── retain
    y = 385
    s.append(txt(40, y + 30, "With retain", 23, INK, "700"))
    s.append(txt(40, y + 54, "KV stays in SRAM", 17, MUTE))
    s.append(txt(40, y + 74, "across the boundary", 17, MUTE))
    s += seg(X0, 2 * SEG * PX, y, 112, GREEN, GREEN_D, 0.70, "inherited — 512 tokens of KV kept",
             "zero work")
    s += seg(X0 + 2 * SEG * PX, SEG * PX, y, 112, ORANGE, ORANGE_D, 0.85, "256 new steps")
    s.append(txt(X0 + 3 * SEG * PX + 30, y + 32, "256 decode steps", 23, INK, "700"))
    s.append(txt(X0 + 3 * SEG * PX + 30, y + 54, "127.7 M cycles", 18, GREEN_D, "700"))
    s.append(txt(X0 + 3 * SEG * PX + 30, y + 78, "−51.4 %", 24, GREEN_D, "700"))

    s.append(txt(40, 660, "round_reset used to rewind the KV write counter to the fresh prefill "
                          "length. Retain gates that rewind, continues the position encoding, and "
                          "recomputes the remaining steps from the retained length.", 17, MUTE))
    s.append(txt(40, 688, "The host stops re-shipping the prefix each round and sends a "
                          "metadata-only message instead — which meant teaching the transport PEs "
                          "to accept a message carrying no data at all.", 17, MUTE))

    s.append('</g></svg>')
    return "\n".join(x for x in s if x)


for name, gen in (("diag_prefill", prefill), ("diag_decode", decode)):
    p = os.path.join(OUT, name + ".svg")
    open(p, "w").write(gen())
    os.system(f'inkscape "{p}" --export-type=png --export-dpi=192 '
              f'--export-filename="{os.path.join(OUT, name)}.png" 2>/dev/null')
    print("wrote", name)
