"""Rules R3, R4, R8."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from rt_imaging_mcp.security.errors import (
    InvalidPathError,
    PathNotFoundError,
    PathOutsideRootError,
    WrongPathKindError,
)
from rt_imaging_mcp.security.paths import resolve_in_root, to_relative, walk_files

needs_symlinks = pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privileges")


def test_relative_file_inside_root_is_resolved(root: Path) -> None:
    (root / "a").mkdir()
    target = root / "a" / "file.bin"
    target.write_bytes(b"x")
    assert resolve_in_root(root, "a/file.bin", kind="file") == target


def test_absolute_path_inside_root_is_accepted(root: Path) -> None:
    target = root / "file.bin"
    target.write_bytes(b"x")
    assert resolve_in_root(root, str(target), kind="file") == target


@pytest.mark.parametrize("bad", ["", "   ", "a\x00b"])
def test_invalid_strings_rejected(root: Path, bad: str) -> None:
    with pytest.raises(InvalidPathError):
        resolve_in_root(root, bad)


@pytest.mark.parametrize("bad", ["..", "../x", "a/../b", "a/.."])
def test_dotdot_segments_rejected_even_if_they_stay_inside(root: Path, bad: str) -> None:
    (root / "a").mkdir()
    (root / "b").mkdir()
    with pytest.raises(InvalidPathError):
        resolve_in_root(root, bad)


def test_absolute_path_outside_root_rejected(root: Path, outside: Path) -> None:
    with pytest.raises(PathOutsideRootError):
        resolve_in_root(root, str(outside / "secret.txt"))


def test_no_existence_oracle_outside_root(root: Path, outside: Path) -> None:
    """Existing and non-existing paths outside the root fail with the same error."""
    with pytest.raises(PathOutsideRootError):
        resolve_in_root(root, str(outside / "secret.txt"))
    with pytest.raises(PathOutsideRootError):
        resolve_in_root(root, str(outside / "does-not-exist.txt"))


@needs_symlinks
def test_symlink_to_file_outside_root_rejected(root: Path, outside: Path) -> None:
    os.symlink(outside / "secret.txt", root / "link.txt")
    with pytest.raises(PathOutsideRootError):
        resolve_in_root(root, "link.txt")


@needs_symlinks
def test_symlink_to_directory_outside_root_rejected(root: Path, outside: Path) -> None:
    os.symlink(outside, root / "linkdir", target_is_directory=True)
    with pytest.raises(PathOutsideRootError):
        resolve_in_root(root, "linkdir/secret.txt")


def test_missing_path_inside_root(root: Path) -> None:
    with pytest.raises(PathNotFoundError):
        resolve_in_root(root, "nope.bin")


def test_kind_is_enforced(root: Path) -> None:
    (root / "d").mkdir()
    (root / "f").write_bytes(b"x")
    with pytest.raises(WrongPathKindError):
        resolve_in_root(root, "d", kind="file")
    with pytest.raises(WrongPathKindError):
        resolve_in_root(root, "f", kind="dir")


def test_error_messages_are_static(root: Path) -> None:
    secret_name = "Budi_Santoso_CT_2024"
    with pytest.raises(PathNotFoundError) as info:
        resolve_in_root(root, secret_name)
    assert secret_name not in str(info.value)
    assert str(root) not in str(info.value)


def test_to_relative_never_returns_absolute_path(root: Path) -> None:
    target = root / "sub" / "file.bin"
    target.parent.mkdir()
    target.write_bytes(b"x")
    relative = to_relative(root, target)
    assert relative == "sub/file.bin"
    assert not Path(relative).is_absolute()
    assert str(root) not in relative
    assert to_relative(root, root) == "."


def test_to_relative_rejects_outside_path(root: Path, outside: Path) -> None:
    with pytest.raises(PathOutsideRootError):
        to_relative(root, outside / "secret.txt")


def test_walk_returns_sorted_files(root: Path) -> None:
    (root / "b").mkdir()
    (root / "b" / "2.bin").write_bytes(b"x")
    (root / "a.bin").write_bytes(b"x")
    (root / "b" / "1.bin").write_bytes(b"x")
    result = walk_files(root, root, max_depth=5, max_files=100)
    names = [p.relative_to(root).as_posix() for p in result.files]
    assert names == ["a.bin", "b/1.bin", "b/2.bin"]
    assert result.truncated is False


def test_walk_stops_at_max_files(root: Path) -> None:
    for index in range(10):
        (root / f"f{index}.bin").write_bytes(b"x")
    result = walk_files(root, root, max_depth=5, max_files=3)
    assert len(result.files) == 3
    assert result.truncated is True


def test_walk_exactly_at_limit_is_not_truncated(root: Path) -> None:
    for index in range(3):
        (root / f"f{index}.bin").write_bytes(b"x")
    result = walk_files(root, root, max_depth=5, max_files=3)
    assert len(result.files) == 3
    assert result.truncated is False


def test_walk_respects_max_depth(root: Path) -> None:
    deep = root / "d1" / "d2" / "d3"
    deep.mkdir(parents=True)
    (deep / "deep.bin").write_bytes(b"x")
    (root / "d1" / "shallow.bin").write_bytes(b"x")
    result = walk_files(root, root, max_depth=1, max_files=100)
    names = [p.name for p in result.files]
    assert names == ["shallow.bin"]
    assert result.truncated is True


@needs_symlinks
def test_walk_never_follows_or_returns_symlinks(root: Path, outside: Path) -> None:
    os.symlink(outside, root / "linkdir", target_is_directory=True)
    os.symlink(outside / "secret.txt", root / "link.txt")
    (root / "real.bin").write_bytes(b"x")
    result = walk_files(root, root, max_depth=5, max_files=100)
    assert [p.name for p in result.files] == ["real.bin"]


def test_walk_rejects_start_outside_root(root: Path, outside: Path) -> None:
    with pytest.raises(PathOutsideRootError):
        walk_files(outside, root, max_depth=5, max_files=10)
