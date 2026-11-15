"""rt_structure_summary: rules R1, R2, R3, R6, R8, R10 and basic geometry accuracy."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rt_imaging_mcp.config import Config
from rt_imaging_mcp.security.errors import (
    FileTooLargeError,
    NotDicomError,
    NotRtStructError,
    PathOutsideRootError,
)
from rt_imaging_mcp.tools.rt import MAX_ROIS, rt_structure_summary
from tests.synthetic import (
    FAKE_ROI_NAME,
    RT_IDENTIFYING_VALUES,
    RoiSpec,
    extrude,
    square,
    write_dicom,
    write_rtstruct,
)


@pytest.fixture
def rtstruct(root: Path) -> Path:
    z_cube = [float(z) for z in range(10)]  # 10 slices, 1 mm apart
    z_tube = [0.0, 2.0, 4.0, 6.0, 8.0]  # 5 slices, 2 mm apart
    rois = [
        RoiSpec(1, "PTV_5000", "PTV", "MANUAL", extrude(square(0, 0, 10), z_cube)),
        RoiSpec(
            2,
            "Rectum",
            "ORGAN",
            "AUTOMATIC",
            [
                (z, polygon)
                for z in z_tube
                for polygon in (square(0, 0, 20), square(5, 5, 10))  # outer square with a hole
            ],
        ),
        RoiSpec(3, FAKE_ROI_NAME, "ORGAN", "SEMIAUTOMATIC", extrude(square(0, 0, 4), [0.0, 1.0])),
        RoiSpec(4, "Bladder", "NOT_A_REAL_TYPE", "MANUAL", []),
    ]
    return write_rtstruct(root / "struct.dcm", rois)


def by_number(summary: dict, number: int) -> dict:  # type: ignore[type-arg]
    return next(roi for roi in summary["rois"] if roi["roi_number"] == number)


def test_summary_overview(root: Path, rtstruct: Path) -> None:
    summary = rt_structure_summary(Config.from_root(root), "struct.dcm")
    assert summary["roi_count"] == 4
    assert [r["roi_number"] for r in summary["rois"]] == [1, 2, 3, 4]
    assert summary["truncated"] is False
    assert summary["counts_by_interpreted_type"] == {"ORGAN": 2, "PTV": 1, "UNKNOWN": 1}


def test_cube_volume_and_extent(root: Path, rtstruct: Path) -> None:
    roi = by_number(rt_structure_summary(Config.from_root(root), "struct.dcm"), 1)
    # 10 slices x 100 mm^2 x 1 mm = 1000 mm^3 = 1 cm^3
    assert roi["approx_volume_cm3"] == pytest.approx(1.0)
    assert roi["slice_count"] == 10
    assert roi["contour_count"] == 10
    assert roi["extent_mm"] == [10.0, 10.0, 9.0]
    assert roi["geometric_types"] == ["CLOSED_PLANAR"]
    assert roi["generation_algorithm"] == "MANUAL"
    assert roi["interpreted_type"] == "PTV"


def test_hole_is_subtracted_in_volume(root: Path, rtstruct: Path) -> None:
    roi = by_number(rt_structure_summary(Config.from_root(root), "struct.dcm"), 2)
    # (400 - 100) mm^2 x 5 slices x 2 mm = 3000 mm^3 = 3 cm^3
    assert roi["approx_volume_cm3"] == pytest.approx(3.0)
    assert roi["slice_count"] == 5
    assert roi["contour_count"] == 10


def test_standard_names_are_returned_others_redacted(root: Path, rtstruct: Path) -> None:
    summary = rt_structure_summary(Config.from_root(root), "struct.dcm")
    assert by_number(summary, 1)["name"] == "PTV_5000"
    assert by_number(summary, 2)["name"] == "Rectum"
    redacted = by_number(summary, 3)
    assert redacted["name"] is None
    assert redacted["name_redacted"] is True
    assert by_number(summary, 1)["name_redacted"] is False


def test_operator_can_enable_a_name(root: Path, rtstruct: Path) -> None:
    config = Config.from_root(root, extra_roi_names=frozenset({FAKE_ROI_NAME}))
    roi = by_number(rt_structure_summary(config, "struct.dcm"), 3)
    assert roi["name"] == FAKE_ROI_NAME
    assert roi["name_redacted"] is False


def test_structure_without_contours(root: Path, rtstruct: Path) -> None:
    roi = by_number(rt_structure_summary(Config.from_root(root), "struct.dcm"), 4)
    assert roi["contour_count"] == 0
    assert roi["slice_count"] == 0
    assert roi["approx_volume_cm3"] is None
    assert roi["extent_mm"] is None
    assert roi["interpreted_type"] is None  # unknown code string is not echoed


def test_single_slice_has_no_volume(root: Path) -> None:
    rois = [RoiSpec(1, "PTV", "PTV", "MANUAL", extrude(square(0, 0, 10), [0.0]))]
    write_rtstruct(root / "one.dcm", rois)
    roi = rt_structure_summary(Config.from_root(root), "one.dcm")["rois"][0]
    assert roi["approx_volume_cm3"] is None
    assert roi["slice_count"] == 1


def test_no_identifiers_free_text_or_coordinates_in_output(root: Path, rtstruct: Path) -> None:
    serialized = json.dumps(rt_structure_summary(Config.from_root(root), "struct.dcm"))
    for value in RT_IDENTIFYING_VALUES:
        assert value not in serialized
    assert "ContourData" not in serialized
    assert "NOT_A_REAL_TYPE" not in serialized


def test_output_is_json_serializable(root: Path, rtstruct: Path) -> None:
    json.dumps(rt_structure_summary(Config.from_root(root), "struct.dcm"), allow_nan=False)


def test_non_rtstruct_dicom_rejected(root: Path) -> None:
    write_dicom(root / "ct.dcm")
    with pytest.raises(NotRtStructError):
        rt_structure_summary(Config.from_root(root), "ct.dcm")


def test_non_dicom_rejected(root: Path) -> None:
    (root / "x.txt").write_text("nope")
    with pytest.raises(NotDicomError):
        rt_structure_summary(Config.from_root(root), "x.txt")


def test_too_large_rejected(root: Path, rtstruct: Path) -> None:
    with pytest.raises(FileTooLargeError):
        rt_structure_summary(Config.from_root(root, max_file_bytes=100), "struct.dcm")


def test_outside_root_rejected(root: Path, outside: Path) -> None:
    write_rtstruct(outside / "s.dcm", [RoiSpec(1, "PTV")])
    with pytest.raises(PathOutsideRootError):
        rt_structure_summary(Config.from_root(root), str(outside / "s.dcm"))


def test_roi_count_is_bounded(root: Path) -> None:
    rois = [RoiSpec(number, "PTV") for number in range(1, MAX_ROIS + 6)]
    write_rtstruct(root / "many.dcm", rois)
    summary = rt_structure_summary(Config.from_root(root), "many.dcm")
    assert summary["truncated"] is True
    assert len(summary["rois"]) == MAX_ROIS
    assert summary["roi_count"] == MAX_ROIS + 5


def test_error_messages_are_static(root: Path) -> None:
    write_dicom(root / "SECRETNAME.dcm")
    with pytest.raises(NotRtStructError) as info:
        rt_structure_summary(Config.from_root(root), "SECRETNAME.dcm")
    assert "SECRETNAME" not in str(info.value)
