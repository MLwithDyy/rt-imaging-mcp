"""Safe path handling (rules R3, R4, R8).

All path arguments from a client go through ``resolve_in_root``. Paths that are
returned to a client go through ``to_relative``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from rt_imaging_mcp.security.errors import (
    InvalidPathError,
    PathNotFoundError,
    PathOutsideRootError,
    WrongPathKindError,
)

PathKind = Literal["file", "dir", "any"]


def resolve_in_root(root: Path, user_path: str, kind: PathKind = "any") -> Path:
    """Resolve a client-supplied path and make sure it stays inside ``root``.

    - Relative paths are interpreted relative to ``root``.
    - Absolute paths are accepted only if they resolve inside ``root``.
    - ``..`` segments are rejected outright.
    - Symlinks are resolved first, so a link pointing outside the root is rejected.
    - Containment is checked before existence, so the error does not reveal whether
      a file outside the root exists.
    """
    if not isinstance(user_path, str) or not user_path.strip() or "\x00" in user_path:
        raise InvalidPathError()

    candidate = Path(user_path)
    if ".." in candidate.parts:
        raise InvalidPathError()

    resolved_root = root.resolve()
    try:
        resolved = (resolved_root / candidate).resolve(strict=False)
    except (OSError, RuntimeError):
        raise InvalidPathError() from None

    if not resolved.is_relative_to(resolved_root):
        raise PathOutsideRootError()
    if not resolved.exists():
        raise PathNotFoundError()

    if kind == "file" and not resolved.is_file():
        raise WrongPathKindError()
    if kind == "dir" and not resolved.is_dir():
        raise WrongPathKindError()
    if not (resolved.is_file() or resolved.is_dir()):
        raise WrongPathKindError()
    return resolved


def to_relative(root: Path, path: Path) -> str:
    """Return ``path`` relative to ``root`` in POSIX form. Never returns an absolute path."""
    try:
        relative = path.resolve().relative_to(root.resolve())
    except ValueError:
        raise PathOutsideRootError() from None
    return relative.as_posix()


@dataclass(frozen=True)
class WalkResult:
    files: list[Path]
    truncated: bool


def walk_files(start: Path, root: Path, *, max_depth: int, max_files: int) -> WalkResult:
    """Collect regular files below ``start`` with hard limits.

    Symlinks (files and directories) are never followed or returned. Output order is
    deterministic. ``truncated`` is True when a limit stopped the walk.
    """
    resolved_root = root.resolve()
    resolved_start = start.resolve()
    if not resolved_start.is_relative_to(resolved_root):
        raise PathOutsideRootError()

    files: list[Path] = []
    truncated = False

    def visit(directory: Path, depth: int) -> bool:
        """Return False when the walk must stop."""
        nonlocal truncated
        try:
            with os.scandir(directory) as iterator:
                entries = sorted(iterator, key=lambda entry: entry.name)
        except OSError:
            return True

        for entry in entries:
            if entry.is_symlink():
                continue
            if entry.is_file(follow_symlinks=False):
                if len(files) >= max_files:
                    truncated = True
                    return False
                files.append(Path(entry.path))
            elif entry.is_dir(follow_symlinks=False):
                if depth >= max_depth:
                    truncated = True
                    continue
                if not visit(Path(entry.path), depth + 1):
                    return False
        return True

    visit(resolved_start, 0)
    return WalkResult(files=files, truncated=truncated)
