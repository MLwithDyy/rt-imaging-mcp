"""Documents written for readers must not be committed with unfilled placeholders."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
STORY = REPO / "docs" / "validation-story.md"


@pytest.mark.skipif(not STORY.is_file(), reason="the write-up is not part of this checkout")
def test_the_write_up_has_no_unfilled_placeholders() -> None:
    text = STORY.read_text(encoding="utf-8")
    assert "<<" not in text, "fill in the data citation and remove the marker"
    assert ">>" not in text
    assert "[tautan" not in text
