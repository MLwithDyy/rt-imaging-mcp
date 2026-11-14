#!/usr/bin/env python3
"""Pre-commit guard: refuse to commit files that look like medical image data.

DICOM files often have no extension, so besides checking suffixes this script
looks for the DICOM magic bytes ("DICM" at byte offset 128).

Usage (done by pre-commit): python scripts/check_no_medical_images.py FILE...
Exit code 1 means at least one file was blocked.
"""

from __future__ import annotations

import sys
from pathlib import Path

BLOCKED_SUFFIXES = (
    ".dcm",
    ".dicom",
    ".nii",
    ".nii.gz",
    ".mha",
    ".mhd",
    ".nrrd",
)
BLOCKED_NAMES = ("DICOMDIR",)
DICOM_MAGIC_OFFSET = 128
DICOM_MAGIC = b"DICM"


def has_dicom_magic(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            handle.seek(DICOM_MAGIC_OFFSET)
            return handle.read(len(DICOM_MAGIC)) == DICOM_MAGIC
    except OSError:
        return False


def blocked_reason(path: Path) -> str | None:
    name = path.name
    if name in BLOCKED_NAMES:
        return "DICOMDIR index file"
    if name.lower().endswith(BLOCKED_SUFFIXES):
        return "medical image file extension"
    if path.is_file() and has_dicom_magic(path):
        return "DICOM magic bytes found"
    return None


def main(argv: list[str]) -> int:
    failed = False
    for arg in argv:
        reason = blocked_reason(Path(arg))
        if reason is not None:
            print(f"BLOCKED: {arg} ({reason})", file=sys.stderr)
            failed = True
    if failed:
        print(
            "\nMedical image data must never be committed. "
            "Keep it outside the repository and generate synthetic data in tests.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
