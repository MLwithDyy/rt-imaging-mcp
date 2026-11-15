"""DICOM tools: rules R1, R2, R3, R4, R6, R8."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydicom.uid import generate_uid

from rt_imaging_mcp.config import Config
from rt_imaging_mcp.security.errors import (
    FileTooLargeError,
    NotDicomError,
    PathOutsideRootError,
    TagNotAllowedError,
)
from rt_imaging_mcp.tools.dicom import (
    dicom_get_metadata,
    dicom_list_allowed_tags,
    dicom_scan_directory,
)
from tests.synthetic import FAKE_DESCRIPTION, IDENTIFYING_VALUES, write_dicom

PATIENT_FOLDER = "Budi_Santoso_CT_2024"


@pytest.fixture
def populated(root: Path) -> Path:
    series_a, series_b = generate_uid(), generate_uid()
    folder = root / PATIENT_FOLDER
    folder.mkdir()
    write_dicom(folder / "IM0001", SeriesInstanceUID=series_a)
    write_dicom(folder / "IM0002", SeriesInstanceUID=series_a)
    other = root / "other"
    other.mkdir()
    write_dicom(other / "scan.dcm", SeriesInstanceUID=series_b, Modality="MR")
    (root / "notes.txt").write_text("not dicom")
    (folder / "broken").write_bytes(b"\0" * 128 + b"DICM" + b"garbage")
    return root


def _all_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _all_strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _all_strings(v)]
    return []


def test_scan_groups_series_and_counts(populated: Path) -> None:
    result = dicom_scan_directory(Config.from_root(populated))
    assert [s["series_id"] for s in result["series"]] == ["series_001", "series_002"]
    by_count = sorted(result["series"], key=lambda s: s["instance_count"])
    assert [s["instance_count"] for s in by_count] == [1, 2]
    assert {s["modality"] for s in result["series"]} == {"CT", "MR"}
    counts = result["counts"]
    assert counts["dicom_files"] == 3
    assert counts["other_files"] == 1
    assert counts["unreadable_dicom_files"] == 1
    assert result["truncated"] is False


def test_scan_never_returns_uids_or_identifiers(populated: Path) -> None:
    result = dicom_scan_directory(Config.from_root(populated))
    serialized = json.dumps(result)
    for value in IDENTIFYING_VALUES:
        assert value not in serialized
    assert "1.2." not in serialized  # no UID-looking strings


def test_scan_paths_are_relative_never_absolute(populated: Path) -> None:
    result = dicom_scan_directory(Config.from_root(populated))
    for text in _all_strings(result):
        assert str(populated) not in text
        assert not Path(text).is_absolute() or text == "/"


def test_scan_opaque_paths_return_no_names(populated: Path) -> None:
    result = dicom_scan_directory(Config.from_root(populated), opaque_paths=True)
    serialized = json.dumps(result)
    assert PATIENT_FOLDER not in serialized
    assert "IM0001" not in serialized
    assert "scan.dcm" not in serialized
    assert all(s["directory"] is None and s["first_file"] is None for s in result["series"])
    assert result["directory"] is None


def test_scan_default_shows_relative_names(populated: Path) -> None:
    """Documents the known trade-off: default output includes names relative to the root."""
    result = dicom_scan_directory(Config.from_root(populated))
    assert PATIENT_FOLDER in json.dumps(result)


def test_scan_respects_max_files(populated: Path) -> None:
    result = dicom_scan_directory(Config.from_root(populated, max_files=2))
    assert result["truncated"] is True
    assert result["counts"]["files_visited"] == 2


def test_scan_skips_files_over_size_limit(populated: Path) -> None:
    result = dicom_scan_directory(Config.from_root(populated, max_file_bytes=100))
    assert result["counts"]["skipped_too_large"] >= 3
    assert result["counts"]["dicom_files"] == 0


def test_scan_rejects_directory_outside_root(populated: Path, outside: Path) -> None:
    with pytest.raises(PathOutsideRootError):
        dicom_scan_directory(Config.from_root(populated), str(outside))


def test_scan_subdirectory(populated: Path) -> None:
    result = dicom_scan_directory(Config.from_root(populated), "other")
    assert [s["modality"] for s in result["series"]] == ["MR"]
    assert result["directory"] == "other"


def test_metadata_default_returns_only_technical_attributes(populated: Path) -> None:
    result = dicom_get_metadata(Config.from_root(populated), "other/scan.dcm")
    metadata = result["metadata"]
    assert metadata["Modality"] == "MR"
    assert metadata["Rows"] == 4
    assert metadata["PixelSpacing"] == [0.5, 0.5]
    serialized = json.dumps(result)
    for value in IDENTIFYING_VALUES:
        assert value not in serialized
    assert FAKE_DESCRIPTION not in serialized
    assert "PixelData" not in metadata


def test_metadata_does_not_echo_the_path(populated: Path) -> None:
    result = dicom_get_metadata(Config.from_root(populated), f"{PATIENT_FOLDER}/IM0001")
    assert PATIENT_FOLDER not in json.dumps(result)


def test_metadata_requested_subset(populated: Path) -> None:
    result = dicom_get_metadata(Config.from_root(populated), "other/scan.dcm", ["Rows", "Columns"])
    assert result["metadata"] == {"Rows": 4, "Columns": 4}


@pytest.mark.parametrize("keyword", ["PatientName", "PatientID", "PixelData", "AccessionNumber"])
def test_metadata_rejects_non_allowlisted_keywords(populated: Path, keyword: str) -> None:
    with pytest.raises(TagNotAllowedError):
        dicom_get_metadata(Config.from_root(populated), "other/scan.dcm", [keyword])


def test_metadata_opt_in_requires_config(populated: Path) -> None:
    plain = Config.from_root(populated)
    with pytest.raises(TagNotAllowedError):
        dicom_get_metadata(plain, "other/scan.dcm", ["StudyDescription"])
    enabled = Config.from_root(populated, enabled_opt_in_tags=frozenset({"StudyDescription"}))
    result = dicom_get_metadata(enabled, "other/scan.dcm", ["StudyDescription"])
    assert result["metadata"]["StudyDescription"] == FAKE_DESCRIPTION


def test_metadata_even_with_all_opt_ins_identifiers_stay_out(populated: Path) -> None:
    from rt_imaging_mcp.security.allowlist import OPT_IN_KEYWORDS

    config = Config.from_root(populated, enabled_opt_in_tags=OPT_IN_KEYWORDS)
    serialized = json.dumps(dicom_get_metadata(config, "other/scan.dcm"))
    for value in IDENTIFYING_VALUES:
        assert value not in serialized


def test_metadata_non_dicom_file(populated: Path) -> None:
    with pytest.raises(NotDicomError):
        dicom_get_metadata(Config.from_root(populated), "notes.txt")


def test_metadata_broken_dicom_file(populated: Path) -> None:
    with pytest.raises(NotDicomError):
        dicom_get_metadata(Config.from_root(populated), f"{PATIENT_FOLDER}/broken")


def test_metadata_too_large(populated: Path) -> None:
    with pytest.raises(FileTooLargeError):
        dicom_get_metadata(Config.from_root(populated, max_file_bytes=100), "other/scan.dcm")


def test_metadata_traversal_rejected(populated: Path) -> None:
    from rt_imaging_mcp.security.errors import InvalidPathError

    with pytest.raises(InvalidPathError):
        dicom_get_metadata(Config.from_root(populated), "../etc/passwd")


def test_list_allowed_tags(populated: Path) -> None:
    config = Config.from_root(populated, enabled_opt_in_tags=frozenset({"StudyDate"}))
    result = dicom_list_allowed_tags(config)
    assert "Modality" in result["default"]
    assert "PatientName" not in result["default"]
    assert result["enabled_opt_in"] == ["StudyDate"]
