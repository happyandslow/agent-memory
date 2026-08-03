#!/usr/bin/env python3
"""Update internal slide 12 without rebuilding the manually edited deck."""

from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DECK = ROOT.parent / "2026-08-02.pptx"
FIGURE = ROOT / "figures" / "lane_b_equations.png"


def replace_once(payload: bytes, old: str, new: str) -> bytes:
    old_bytes = old.encode("utf-8")
    if payload.count(old_bytes) != 1:
        raise RuntimeError(f"expected exactly one occurrence: {old}")
    return payload.replace(old_bytes, new.encode("utf-8"), 1)


with zipfile.ZipFile(DECK) as zin:
    files = {name: zin.read(name) for name in zin.namelist()}

files["ppt/media/image8.png"] = FIGURE.read_bytes()
files["ppt/slides/slide12.xml"] = replace_once(
    files["ppt/slides/slide12.xml"],
    "Delta reload pays I(H); full-context reload pays I(S+H). Both then force-decode Lnew using the Lane A model at absolute prefix S+H.",
    "Lane B reloads the complete target KV: B=I(S+H+Lnew). The next free-decode token is common to both lanes and excluded.",
)
files["ppt/notesSlides/notesSlide12.xml"] = replace_once(
    files["ppt/notesSlides/notesSlide12.xml"],
    "I(h) is piecewise-linear interpolation over the six E5 anchors. E10 validates that the real reload path reproduces E5 and that post-ingress forced-token cost matches E9 to 0.97–1.00 across H=512…8192.",
    "I(h) is piecewise-linear interpolation over the six E5 anchors. Under the current Lane B contract, host memory already holds the complete target KV, so Lane B has no force-decode term. The older E10 delta-reload fixture is a different mechanism and must not be substituted here.",
)

with tempfile.NamedTemporaryFile(
    prefix=DECK.stem + ".", suffix=".pptx", dir=DECK.parent, delete=False
) as handle:
    output = Path(handle.name)
try:
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for name, payload in files.items():
            zout.writestr(name, payload)
    output.replace(DECK)
finally:
    if output.exists():
        output.unlink()

print(f"updated internal slide 12 in {DECK}")
