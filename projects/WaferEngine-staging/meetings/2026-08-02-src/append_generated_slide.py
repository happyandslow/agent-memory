#!/usr/bin/env python3
"""Append slide 1 from a generated one-slide deck to an existing deck."""

from __future__ import annotations

import re
import sys
import tempfile
import zipfile
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: append_generated_slide.py TARGET.pptx SOURCE.pptx")

    target = Path(sys.argv[1])
    source = Path(sys.argv[2])
    with zipfile.ZipFile(target) as zin:
        target_files = {name: zin.read(name) for name in zin.namelist()}
    with zipfile.ZipFile(source) as zin:
        source_files = {name: zin.read(name) for name in zin.namelist()}

    slide_numbers = [
        int(match.group(1))
        for name in target_files
        if (match := re.fullmatch(r"ppt/slides/slide(\d+)\.xml", name))
    ]
    matching_slides = [
        int(match.group(1))
        for name, payload in target_files.items()
        if (match := re.fullmatch(r"ppt/slides/slide(\d+)\.xml", name))
        and b"tracking-derived next actions" in payload.lower()
    ]
    if matching_slides:
        next_slide = matching_slides[-1]
    else:
        next_slide = max(slide_numbers) + 1

    target_files[f"ppt/slides/slide{next_slide}.xml"] = source_files[
        "ppt/slides/slide1.xml"
    ]
    target_files[f"ppt/slides/_rels/slide{next_slide}.xml.rels"] = source_files[
        "ppt/slides/_rels/slide1.xml.rels"
    ].replace(b"notesSlide1.xml", f"notesSlide{next_slide}.xml".encode())
    target_files[f"ppt/notesSlides/notesSlide{next_slide}.xml"] = source_files[
        "ppt/notesSlides/notesSlide1.xml"
    ]
    target_files[
        f"ppt/notesSlides/_rels/notesSlide{next_slide}.xml.rels"
    ] = source_files["ppt/notesSlides/_rels/notesSlide1.xml.rels"].replace(
        b"slide1.xml", f"slide{next_slide}.xml".encode()
    )

    if matching_slides:
        write_deck(target, target_files)
        print(f"replaced slide {next_slide} in {target}")
        return

    rels_name = "ppt/_rels/presentation.xml.rels"
    rels = target_files[rels_name]
    rel_ids = [int(value) for value in re.findall(rb'Id="rId(\d+)"', rels)]
    next_rid = max(rel_ids) + 1
    rel = (
        f'<Relationship Id="rId{next_rid}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" '
        f'Target="slides/slide{next_slide}.xml"/>'
    ).encode()
    target_files[rels_name] = rels.replace(b"</Relationships>", rel + b"</Relationships>")

    presentation_name = "ppt/presentation.xml"
    presentation = target_files[presentation_name]
    slide_ids = [int(value) for value in re.findall(rb'<p:sldId id="(\d+)"', presentation)]
    next_slide_id = max(slide_ids) + 1
    slide_ref = f'<p:sldId id="{next_slide_id}" r:id="rId{next_rid}"/>'.encode()
    target_files[presentation_name] = presentation.replace(
        b"</p:sldIdLst>", slide_ref + b"</p:sldIdLst>"
    )

    content_types_name = "[Content_Types].xml"
    content_types = target_files[content_types_name]
    overrides = (
        f'<Override PartName="/ppt/slides/slide{next_slide}.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
        f'<Override PartName="/ppt/notesSlides/notesSlide{next_slide}.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.presentationml.notesSlide+xml"/>'
    ).encode()
    target_files[content_types_name] = content_types.replace(b"</Types>", overrides + b"</Types>")

    write_deck(target, target_files)
    print(f"appended slide {next_slide} to {target}")


def write_deck(target: Path, target_files: dict[str, bytes]) -> None:
    with tempfile.NamedTemporaryFile(
        prefix=target.stem + ".", suffix=".pptx", dir=target.parent, delete=False
    ) as handle:
        output = Path(handle.name)
    try:
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for name, payload in target_files.items():
                zout.writestr(name, payload)
        output.replace(target)
    finally:
        if output.exists():
            output.unlink()

if __name__ == "__main__":
    main()
