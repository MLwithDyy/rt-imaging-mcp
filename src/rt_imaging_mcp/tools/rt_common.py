"""Shared helpers for the radiotherapy tools.

RT objects only return numbers and DICOM enumerated code strings (rule R11).
``code`` maps a code string to itself only when it is on the given allowlist,
so free text hidden in a code field is never echoed.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pydicom

from rt_imaging_mcp.config import Config
from rt_imaging_mcp.security.errors import FileTooLargeError, NotDicomError
from rt_imaging_mcp.security.paths import resolve_in_root
from rt_imaging_mcp.tools.dicom import has_dicom_preamble

RT_MAX_BYTES = 256 * 1024 * 1024


def code(value: Any, allowed: frozenset[str]) -> str | None:
    """Return an enumerated DICOM code string if it is on the allowlist, else ``None``."""
    if value is None:
        return None
    text = str(value).strip().upper()
    return text if text in allowed else None


def number(value: Any) -> float | None:
    """Return a finite float, or ``None`` for missing, non-numeric or non-finite values."""
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def prepare_rt_file(config: Config, path: str) -> Path:
    """Resolve the path and apply the size and format pre-checks shared by RT tools."""
    file = resolve_in_root(config.root, path, kind="file")
    if file.stat().st_size > min(config.max_file_bytes, RT_MAX_BYTES):
        raise FileTooLargeError()
    if not has_dicom_preamble(file):
        raise NotDicomError()
    return file


def read_with_pixels(file: Path) -> Any:
    """Read a whole DICOM file including pixel data. Failures become a static error."""
    try:
        dataset = pydicom.dcmread(file)
    except Exception:
        raise NotDicomError() from None
    if "TransferSyntaxUID" not in dataset.file_meta:
        raise NotDicomError()
    return dataset


def contour_polygon(item: Any) -> tuple[float, Any] | None:
    """Return ``(z, xy_polygon)`` for a closed planar contour, else ``None``.

    ``z`` is the mean z of the contour points rounded to 0.01 mm, the same rule that
    ``rt_structure_summary`` uses to group contours into slices.
    """
    import numpy as np

    geometric = code(item.get("ContourGeometricType"), frozenset({"CLOSED_PLANAR"}))
    if geometric is None:
        return None
    try:
        points = np.asarray(item.get("ContourData"), dtype=float).reshape(-1, 3)
    except (TypeError, ValueError):
        return None
    if len(points) < 3 or not np.all(np.isfinite(points)):
        return None
    return round(float(points[:, 2].mean()), 2), points[:, :2]
