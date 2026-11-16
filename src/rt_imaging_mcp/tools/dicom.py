"""DICOM tools: scan a directory, read allowlisted metadata, list allowed tags."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pydicom

from rt_imaging_mcp.config import Config
from rt_imaging_mcp.security.allowlist import (
    DEFAULT_KEYWORDS,
    filter_dataset,
    resolve_keywords,
    to_jsonable,
)
from rt_imaging_mcp.security.errors import FileTooLargeError, NotDicomError
from rt_imaging_mcp.security.paths import resolve_in_root, to_relative, walk_files

_DICOM_MAGIC_OFFSET = 128
_DICOM_MAGIC = b"DICM"

# Read only to group instances into series. UIDs are used internally and never returned (R1).
_SCAN_TAGS = ["Modality", "SeriesInstanceUID", "Rows", "Columns"]


def has_dicom_preamble(path: Path) -> bool:
    """True when the file has the DICOM Part 10 preamble ("DICM" at byte 128)."""
    try:
        with path.open("rb") as handle:
            handle.seek(_DICOM_MAGIC_OFFSET)
            return handle.read(len(_DICOM_MAGIC)) == _DICOM_MAGIC
    except OSError:
        return False


def read_header(path: Path, specific_tags: list[str] | None = None) -> Any:
    """Read a DICOM header without pixel data. Any failure becomes a static error."""
    try:
        header = pydicom.dcmread(path, stop_before_pixels=True, specific_tags=specific_tags)
    except Exception:
        raise NotDicomError() from None
    # A Part 10 file must carry a transfer syntax in its file meta. Without it the file only
    # has the preamble bytes and is not a usable DICOM file.
    if "TransferSyntaxUID" not in header.file_meta:
        raise NotDicomError()
    return header


@dataclass
class _Series:
    modality: str | None
    rows: int | None
    columns: int | None
    first_file: Path
    count: int = 1


def dicom_scan_directory(
    config: Config, directory: str = ".", opaque_paths: bool = False
) -> dict[str, Any]:
    """Inventory DICOM series below ``directory`` (relative to the configured root).

    Only DICOM Part 10 files (with the "DICM" preamble) are recognised. Series are
    returned with opaque ids (``series_001``). Study and series UIDs are never returned.
    With ``opaque_paths=True`` no directory or file names are returned at all.
    """
    start = resolve_in_root(config.root, directory, kind="dir")
    walk = walk_files(start, config.root, max_depth=config.max_depth, max_files=config.max_files)

    groups: dict[tuple[str, str, str], _Series] = {}
    dicom_files = other_files = unreadable = too_large = 0

    for file in walk.files:
        try:
            if file.stat().st_size > config.max_file_bytes:
                too_large += 1
                continue
        except OSError:
            other_files += 1
            continue
        if not has_dicom_preamble(file):
            other_files += 1
            continue
        try:
            header = read_header(file, _SCAN_TAGS)
        except NotDicomError:
            unreadable += 1
            continue

        dicom_files += 1
        series_uid = str(header.get("SeriesInstanceUID", "") or "")
        modality = to_jsonable(header.get("Modality"))
        # The modality is part of the key: files without a series UID never merge across modalities.
        key = (str(file.parent), series_uid, modality if isinstance(modality, str) else "")
        existing = groups.get(key)
        if existing is not None:
            existing.count += 1
            continue
        rows = to_jsonable(header.get("Rows"))
        columns = to_jsonable(header.get("Columns"))
        groups[key] = _Series(
            modality=modality if isinstance(modality, str) else None,
            rows=rows if isinstance(rows, int) else None,
            columns=columns if isinstance(columns, int) else None,
            first_file=file,
        )

    series: list[dict[str, Any]] = []
    for index, key in enumerate(sorted(groups), start=1):
        item = groups[key]
        series.append(
            {
                "series_id": f"series_{index:03d}",
                "modality": item.modality,
                "instance_count": item.count,
                "rows": item.rows,
                "columns": item.columns,
                "directory": None
                if opaque_paths
                else to_relative(config.root, item.first_file.parent),
                "first_file": None if opaque_paths else to_relative(config.root, item.first_file),
            }
        )

    return {
        "directory": None if opaque_paths else to_relative(config.root, start),
        "series": series,
        "counts": {
            "files_visited": len(walk.files),
            "dicom_files": dicom_files,
            "other_files": other_files,
            "unreadable_dicom_files": unreadable,
            "skipped_too_large": too_large,
        },
        "truncated": walk.truncated,
        "limits": {
            "max_files": config.max_files,
            "max_depth": config.max_depth,
            "max_file_bytes": config.max_file_bytes,
        },
    }


def dicom_get_metadata(
    config: Config, path: str, keywords: list[str] | None = None
) -> dict[str, Any]:
    """Return allowlisted DICOM attributes of one file.

    ``keywords=None`` returns every currently allowed attribute that the file contains.
    Requesting any attribute that is not allowed fails (R1). Pixel data is never read (R2).
    The file path is not echoed back.
    """
    file = resolve_in_root(config.root, path, kind="file")
    if file.stat().st_size > config.max_file_bytes:
        raise FileTooLargeError()
    if not has_dicom_preamble(file):
        raise NotDicomError()

    allowed = resolve_keywords(keywords, config.enabled_opt_in_tags)
    header = read_header(file)
    return {"metadata": filter_dataset(header, allowed)}


def dicom_list_allowed_tags(config: Config) -> dict[str, Any]:
    """List the attribute keywords that ``dicom_get_metadata`` can currently return."""
    return {
        "default": sorted(DEFAULT_KEYWORDS),
        "enabled_opt_in": sorted(config.enabled_opt_in_tags),
    }
