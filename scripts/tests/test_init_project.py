import subprocess, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]

def test_template_has_capture_and_meetings():
    tpl = REPO / "projects" / "_template"
    assert (tpl / "capture.md").is_file()
    assert (tpl / "meetings" / "README.md").is_file()

def test_template_views_have_generated_header():
    tpl = REPO / "projects" / "_template"
    for f in ("memory/context.md", "tracking/status.md", "index.md"):
        assert (tpl / f).read_text().startswith("<!-- GENERATED")
