"""Rule R3 (no default root) and R8 (limits)."""

from __future__ import annotations

from pathlib import Path

import pytest

from rt_imaging_mcp.config import ENV_ROOT, Config
from rt_imaging_mcp.security.errors import ConfigError


def test_from_root_resolves_directory(root: Path) -> None:
    config = Config.from_root(root)
    assert config.root == root
    assert config.max_files > 0


def test_missing_root_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        Config.from_root(tmp_path / "does-not-exist")


def test_file_as_root_rejected(tmp_path: Path) -> None:
    file_path = tmp_path / "f.txt"
    file_path.write_text("x")
    with pytest.raises(ConfigError):
        Config.from_root(file_path)


def test_no_default_root_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_ROOT, raising=False)
    with pytest.raises(ConfigError):
        Config.from_env()


def test_root_from_env(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    monkeypatch.setenv(ENV_ROOT, str(root))
    assert Config.from_env().root == root


@pytest.mark.parametrize("field", ["max_files", "max_file_bytes"])
def test_non_positive_limits_rejected(root: Path, field: str) -> None:
    with pytest.raises(ConfigError):
        Config.from_root(root, **{field: 0})


def test_negative_depth_rejected(root: Path) -> None:
    with pytest.raises(ConfigError):
        Config.from_root(root, max_depth=-1)


@pytest.mark.parametrize("bad", ["", "   ", "x" * 65])
def test_invalid_extra_roi_names_rejected(root: Path, bad: str) -> None:
    with pytest.raises(ConfigError):
        Config.from_root(root, extra_roi_names=frozenset({bad}))


def test_extra_roi_names_accepted(root: Path) -> None:
    config = Config.from_root(root, extra_roi_names=frozenset({"Rectum_Spare"}))
    assert config.extra_roi_names == frozenset({"Rectum_Spare"})
