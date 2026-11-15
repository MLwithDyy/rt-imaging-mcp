from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """A resolved temporary directory used as the configured root."""
    resolved = (tmp_path / "root").resolve()
    resolved.mkdir()
    return resolved


@pytest.fixture
def outside(tmp_path: Path) -> Path:
    """A directory next to the root, outside it."""
    path = (tmp_path / "outside").resolve()
    path.mkdir()
    (path / "secret.txt").write_text("outside secret")
    return path
