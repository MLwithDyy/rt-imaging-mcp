"""rt_dvh_metrics: analytic phantoms, independent brute force, security and limits."""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from rt_imaging_mcp.config import Config
from rt_imaging_mcp.geometry import point_in_polygon
from rt_imaging_mcp.security.errors import (
    FileTooLargeError,
    FrameOfReferenceError,
    InvalidParameterError,
    NoStructureVoxelsError,
    NotDicomError,
    NotRtDoseError,
    NotRtStructError,
    PathOutsideRootError,
    StructureNotFoundError,
    UnsupportedGridError,
    WorkLimitError,
)
from rt_imaging_mcp.tools import rt_dvh
from rt_imaging_mcp.tools.rt import rt_structure_summary
from rt_imaging_mcp.tools.rt_dvh import rt_dvh_metrics
from tests.synthetic import (
    ALL_RT_IDENTIFYING_VALUES,
    FAKE_ROI_NAME,
    RoiSpec,
    extrude,
    square,
    write_dicom,
    write_rtdose,
    write_rtstruct,
)

SCALING = 0.001
Z_BOX = [0.0, 2.0, 4.0, 6.0, 8.0]  # contour slices of the reference cube


def cube(name: str = "PTV", number: int = 1) -> RoiSpec:
    """10 x 10 mm squares on five slices 2 mm apart: x, y in [-1, 9], z in [0, 8]."""
    return RoiSpec(number, name, "PTV", "MANUAL", extrude(square(-1, -1, 10), Z_BOX))


def dose_file(
    root: Path,
    frame_doses: Sequence[float],
    *,
    rows: int = 10,
    columns: int = 10,
    name: str = "dose.dcm",
    offsets: Sequence[float] | None = None,
    **kwargs: Any,
) -> Path:
    """RTDOSE with a uniform dose per frame (Gy). Default grid centres: 0, 2, ..., 18 mm."""
    raw = np.empty((len(frame_doses), rows, columns), dtype=np.uint32)
    for frame, gray in enumerate(frame_doses):
        raw[frame] = round(gray / SCALING)
    if offsets is None:
        offsets = [2.0 * index for index in range(len(frame_doses))]
    kwargs.setdefault("pixel_spacing", (2.0, 2.0))
    kwargs.setdefault("origin", (0.0, 0.0, 0.0))
    return write_rtdose(root / name, raw, scaling=SCALING, slice_offsets=offsets, **kwargs)


def struct_file(
    root: Path, rois: Sequence[RoiSpec], name: str = "struct.dcm", **kwargs: Any
) -> Path:
    return write_rtstruct(root / name, rois, **kwargs)


def run(root: Path, roi_number: int = 1, **kwargs: Any) -> dict[str, Any]:
    config = kwargs.pop("config", None) or Config.from_root(root)
    return rt_dvh_metrics(config, "struct.dcm", "dose.dcm", roi_number, **kwargs)


# ------------------------------------------------------------ analytic phantoms


def test_uniform_dose_in_a_cube(root: Path) -> None:
    struct_file(root, [cube()])
    dose_file(root, [20.0] * 6)
    result = run(root, volume_thresholds_gy=[20.0, 20.5])
    assert result["voxel_count"] == 125  # 5 x 5 x 5 voxel centres
    assert result["volume_cm3"] == pytest.approx(1.0)
    assert result["contour_volume_cm3"] == pytest.approx(1.0)
    assert result["inside_grid"] is True
    assert result["dose_gy"] == {"min": 20.0, "max": 20.0, "mean": 20.0}
    assert result["d_metrics_gy"] == {"D95": 20.0, "D50": 20.0, "D2": 20.0}
    assert result["v_metrics"]["V20Gy"] == {"percent": 100.0, "volume_cm3": 1.0}
    assert result["v_metrics"]["V20.5Gy"] == {"percent": 0.0, "volume_cm3": 0.0}
    assert result["dose_units"] == "GY"
    assert result["name"] == "PTV"
    assert result["name_redacted"] is False


def test_gradient_dose_matches_hand_calculation(root: Path) -> None:
    struct_file(root, [cube()])
    dose_file(root, [10.0, 12.0, 14.0, 16.0, 18.0, 20.0])  # the 20 Gy frame is outside the cube
    result = run(root, volume_thresholds_gy=[16.0, 20.0])
    assert result["voxel_count"] == 125
    assert result["dose_gy"] == {"min": 10.0, "max": 18.0, "mean": 14.0}
    assert result["d_metrics_gy"] == {"D95": 10.0, "D50": 14.0, "D2": 18.0}
    assert result["v_metrics"]["V16Gy"] == {"percent": 40.0, "volume_cm3": 0.4}
    assert result["v_metrics"]["V20Gy"]["percent"] == 0.0


def test_hole_is_excluded_from_the_structure(root: Path) -> None:
    outer = square(-1, -1, 10)
    hole = square(1, 1, 6)  # centres 2, 4, 6 -> 3 x 3 voxels per slice
    spec = RoiSpec(1, "Rectum", "ORGAN", "MANUAL", [(z, p) for z in Z_BOX for p in (outer, hole)])
    struct_file(root, [spec])
    raw = np.full((6, 10, 10), round(10.0 / SCALING), dtype=np.uint32)
    raw[:, 1:4, 1:4] = round(50.0 / SCALING)  # the hole voxels carry a much higher dose
    write_rtdose(
        root / "dose.dcm",
        raw,
        scaling=SCALING,
        pixel_spacing=(2.0, 2.0),
        slice_offsets=[0, 2, 4, 6, 8, 10],
        origin=(0.0, 0.0, 0.0),
    )
    result = run(root, volume_thresholds_gy=[10.0])
    assert result["voxel_count"] == 5 * (25 - 9)
    assert result["dose_gy"]["max"] == 10.0
    assert result["volume_cm3"] == pytest.approx(0.64)
    assert result["contour_volume_cm3"] == pytest.approx(0.64)


def test_contour_volume_matches_rt_structure_summary(root: Path) -> None:
    outer, hole = square(-1, -1, 10), square(1, 1, 6)
    spec = RoiSpec(1, "Rectum", "ORGAN", "MANUAL", [(z, p) for z in Z_BOX for p in (outer, hole)])
    struct_file(root, [spec])
    dose_file(root, [10.0] * 6)
    config = Config.from_root(root)
    summary = rt_structure_summary(config, "struct.dcm")["rois"][0]["approx_volume_cm3"]
    assert run(root)["contour_volume_cm3"] == summary == pytest.approx(0.64)


def test_dose_slices_between_contour_slices(root: Path) -> None:
    contours = extrude(square(-1, -1, 10), [0.0, 3.0, 6.0, 9.0])
    struct_file(root, [RoiSpec(1, "PTV", "PTV", "MANUAL", contours)])
    # dose slices at z = 0, 2, ..., 12; the last one is outside the structure
    dose_file(root, [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0])
    result = run(root)
    assert result["voxel_count"] == 6 * 25
    assert result["volume_cm3"] == pytest.approx(1.2)
    assert result["contour_volume_cm3"] == pytest.approx(1.2)
    assert result["dose_gy"]["mean"] == pytest.approx(35.0)
    assert result["dose_gy"]["max"] == 60.0


def test_descending_slice_order_gives_the_same_result(root: Path) -> None:
    struct_file(root, [cube()])
    physical = {z: 10.0 + z for z in (0.0, 2.0, 4.0, 6.0, 8.0, 10.0)}  # dose depends on z only
    dose_file(root, [physical[z] for z in sorted(physical)], name="up.dcm")
    dose_file(
        root,
        [physical[z] for z in sorted(physical, reverse=True)],
        name="down.dcm",
        offsets=[10.0, 8.0, 6.0, 4.0, 2.0, 0.0],
    )
    config = Config.from_root(root)
    ascending = rt_dvh_metrics(config, "struct.dcm", "up.dcm", 1)
    descending = rt_dvh_metrics(config, "struct.dcm", "down.dcm", 1)
    assert ascending == descending
    assert ascending["dose_gy"]["mean"] == pytest.approx(14.0)


def test_grid_origin_is_respected(root: Path) -> None:
    shifted = RoiSpec(
        1, "PTV", "PTV", "MANUAL", extrude(square(99, 49, 10), [30.0, 32.0, 34.0, 36.0, 38.0])
    )
    struct_file(root, [shifted])
    dose_file(root, [10.0, 12.0, 14.0, 16.0, 18.0, 20.0], origin=(100.0, 50.0, 30.0))
    result = run(root)
    assert result["voxel_count"] == 125
    assert result["dose_gy"]["mean"] == pytest.approx(14.0)
    assert result["inside_grid"] is True


def test_x_follows_columns_and_y_follows_rows(root: Path) -> None:
    """A 3 x 5 voxel rectangle (x by y) on a grid with different row and column spacing.

    Columns are 2.0 mm apart (x centres 0, 2, 4), rows are 2.5 mm apart (y centres 0, ..., 10).
    The x range [-1, 4.5] covers three columns only if the column spacing is used for x, and
    the y range [-1.25, 11.25] covers five rows only if the row spacing is used for y.
    """
    rectangle = [(-1.0, -1.25), (4.5, -1.25), (4.5, 11.25), (-1.0, 11.25)]
    spec = RoiSpec(1, "PTV", "PTV", "MANUAL", extrude(rectangle, Z_BOX))
    struct_file(root, [spec])

    by_column = np.zeros((6, 10, 10), dtype=np.uint32)
    by_column[:] = (10 + 2 * np.arange(10))[None, None, :] / SCALING
    by_row = np.zeros((6, 10, 10), dtype=np.uint32)
    by_row[:] = (10 + 2 * np.arange(10))[None, :, None] / SCALING

    common = {
        "scaling": SCALING,
        "pixel_spacing": (2.5, 2.0),  # (row spacing, column spacing)
        "slice_offsets": [0, 2, 4, 6, 8, 10],
        "origin": (0.0, 0.0, 0.0),
    }
    write_rtdose(root / "dose.dcm", by_column, **common)
    columns = run(root)
    write_rtdose(root / "dose.dcm", by_row, **common)
    rows = run(root)

    assert columns["voxel_count"] == rows["voxel_count"] == 3 * 5 * 5
    assert columns["volume_cm3"] == pytest.approx(0.75)  # 75 voxels of 2.0 * 2.5 * 2.0 mm^3
    assert columns["contour_volume_cm3"] == pytest.approx(0.6875, abs=1e-3)  # rounded to 3 digits
    assert columns["dose_gy"]["mean"] == pytest.approx(12.0)  # columns 0..2 -> 10, 12, 14 Gy
    assert rows["dose_gy"]["mean"] == pytest.approx(14.0)  # rows 0..4 -> 10, ..., 18 Gy


def test_structure_partly_outside_the_grid_is_flagged(root: Path) -> None:
    spec = RoiSpec(1, "PTV", "PTV", "MANUAL", extrude(square(11, -1, 10), Z_BOX))  # x in [11, 21]
    struct_file(root, [spec])
    dose_file(root, [10.0] * 6)
    result = run(root)
    assert result["inside_grid"] is False
    assert result["voxel_count"] == 4 * 5 * 5  # centres 12, 14, 16, 18


def test_structure_outside_the_grid_is_an_error(root: Path) -> None:
    spec = RoiSpec(1, "PTV", "PTV", "MANUAL", extrude(square(500, 500, 10), Z_BOX))
    struct_file(root, [spec])
    dose_file(root, [10.0] * 6)
    with pytest.raises(NoStructureVoxelsError):
        run(root)


# ------------------------------------------------------- independent brute force


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_matches_a_voxel_by_voxel_reference(root: Path, seed: int) -> None:
    rng = np.random.default_rng(seed)
    angles = np.sort(rng.uniform(0, 2 * np.pi, size=9))
    radii = rng.uniform(5.0, 8.0, size=9)
    polygon = [(9 + r * np.cos(a), 9 + r * np.sin(a)) for a, r in zip(angles, radii, strict=True)]
    struct_file(root, [RoiSpec(1, "PTV", "PTV", "MANUAL", extrude(polygon, Z_BOX))])

    raw = rng.integers(0, 40_001, size=(6, 10, 10)).astype(np.uint32)
    write_rtdose(
        root / "dose.dcm",
        raw,
        scaling=SCALING,
        pixel_spacing=(2.0, 2.0),
        slice_offsets=[0, 2, 4, 6, 8, 10],
        origin=(0.0, 0.0, 0.0),
    )

    outline = np.array(polygon)
    doses: list[float] = []
    for frame in range(5):  # frame 5 (z = 10) is outside the structure
        for row in range(10):
            for column in range(10):
                if point_in_polygon((2.0 * column, 2.0 * row), outline):
                    doses.append(float(raw[frame, row, column]) * SCALING)
    expected = np.sort(np.array(doses))

    result = run(root, dose_percentages=[95, 50, 2], volume_thresholds_gy=[20.0])
    assert result["voxel_count"] == len(expected) > 20
    assert result["dose_gy"]["mean"] == pytest.approx(expected.mean(), abs=1e-6)
    assert result["dose_gy"]["min"] == pytest.approx(expected[0], abs=1e-6)
    assert result["dose_gy"]["max"] == pytest.approx(expected[-1], abs=1e-6)
    for percent in (95, 50, 2):
        needed = math.ceil(percent * len(expected) / 100 - 1e-9)
        assert result["d_metrics_gy"][f"D{percent}"] == pytest.approx(
            expected[len(expected) - needed], abs=1e-6
        )
    at_least_20 = np.count_nonzero(expected >= 20.0 - 1e-9)
    assert result["v_metrics"]["V20Gy"]["percent"] == pytest.approx(
        100.0 * at_least_20 / len(expected), abs=1e-3
    )


# ------------------------------------------------------------------ parameters


def test_custom_metrics_and_deduplication(root: Path) -> None:
    struct_file(root, [cube()])
    dose_file(root, [10.0, 12.0, 14.0, 16.0, 18.0, 20.0])
    result = run(root, dose_percentages=[90, 2.5, 90], volume_thresholds_gy=[10, 15, 10.0])
    assert list(result["d_metrics_gy"]) == ["D90", "D2.5"]
    assert list(result["v_metrics"]) == ["V10Gy", "V15Gy"]
    assert result["v_metrics"]["V10Gy"]["percent"] == 100.0


def test_empty_metric_lists_are_allowed(root: Path) -> None:
    struct_file(root, [cube()])
    dose_file(root, [10.0] * 6)
    result = run(root, dose_percentages=[], volume_thresholds_gy=[])
    assert result["d_metrics_gy"] == {}
    assert result["v_metrics"] == {}


@pytest.mark.parametrize(
    "kwargs",
    [
        {"dose_percentages": [0]},
        {"dose_percentages": [100.5]},
        {"dose_percentages": [-5]},
        {"dose_percentages": [float("nan")]},
        {"dose_percentages": [float("inf")]},
        {"dose_percentages": ["95"]},
        {"dose_percentages": [True]},
        {"dose_percentages": [None]},
        {"dose_percentages": "95"},
        {"dose_percentages": list(range(1, 22))},
        {"volume_thresholds_gy": [-1]},
        {"volume_thresholds_gy": [1e9]},
        {"volume_thresholds_gy": ["20"]},
        {"volume_thresholds_gy": 20},
    ],
)
def test_invalid_metric_parameters_are_rejected(root: Path, kwargs: dict[str, Any]) -> None:
    struct_file(root, [cube()])
    dose_file(root, [10.0] * 6)
    with pytest.raises(InvalidParameterError):
        run(root, **kwargs)


@pytest.mark.parametrize("roi_number", [True, -1, "1", 1.5, None, 2**31])
def test_invalid_roi_numbers_are_rejected(root: Path, roi_number: Any) -> None:
    struct_file(root, [cube()])
    dose_file(root, [10.0] * 6)
    with pytest.raises(InvalidParameterError):
        run(root, roi_number=roi_number)


# ---------------------------------------------------- inputs that must be refused


def test_unknown_roi(root: Path) -> None:
    struct_file(root, [cube()])
    dose_file(root, [10.0] * 6)
    with pytest.raises(StructureNotFoundError):
        run(root, roi_number=99)


def test_roi_without_contours(root: Path) -> None:
    struct_file(root, [RoiSpec(1, "PTV")])
    dose_file(root, [10.0] * 6)
    with pytest.raises(StructureNotFoundError):
        run(root)


@pytest.mark.parametrize(
    ("struct_frame", "dose_frame"),
    [
        ("1.2.826.0.1.3680043.9.7777.1", "1.2.826.0.1.3680043.9.7777.2"),
        (None, "1.2.826.0.1.3680043.9.7777.424242"),
        ("1.2.826.0.1.3680043.9.7777.424242", None),
        (None, None),
    ],
)
def test_frame_of_reference_must_exist_and_match(
    root: Path, struct_frame: str | None, dose_frame: str | None
) -> None:
    struct_file(root, [cube()], frame_of_reference_uid=struct_frame)
    dose_file(root, [10.0] * 6, frame_of_reference_uid=dose_frame)
    with pytest.raises(FrameOfReferenceError):
        run(root)


def test_relative_dose_is_not_supported(root: Path) -> None:
    struct_file(root, [cube()])
    dose_file(root, [10.0] * 6, DoseUnits="RELATIVE")
    with pytest.raises(UnsupportedGridError):
        run(root)


@pytest.mark.parametrize(
    "orientation", [[0, 1, 0, 1, 0, 0], [-1, 0, 0, 0, -1, 0], [1, 0, 0, 0, 0, 1]]
)
def test_rotated_dose_grids_are_not_supported(root: Path, orientation: list[int]) -> None:
    struct_file(root, [cube()])
    dose_file(root, [10.0] * 6, ImageOrientationPatient=orientation)
    with pytest.raises(UnsupportedGridError):
        run(root)


def test_non_uniform_slice_spacing_is_not_supported(root: Path) -> None:
    struct_file(root, [cube()])
    dose_file(root, [10.0] * 4, offsets=[0.0, 2.0, 5.0, 6.0])
    with pytest.raises(UnsupportedGridError):
        run(root)


def test_single_frame_dose_is_not_supported(root: Path) -> None:
    struct_file(root, [cube()])
    dose_file(root, [10.0])
    with pytest.raises(UnsupportedGridError):
        run(root)


def test_files_of_the_wrong_kind(root: Path) -> None:
    struct_file(root, [cube()])
    dose_file(root, [10.0] * 6)
    write_dicom(root / "ct.dcm")
    (root / "x.txt").write_text("nope")
    config = Config.from_root(root)
    with pytest.raises(NotRtStructError):
        rt_dvh_metrics(config, "dose.dcm", "dose.dcm", 1)
    with pytest.raises(NotRtDoseError):
        rt_dvh_metrics(config, "struct.dcm", "struct.dcm", 1)
    with pytest.raises(NotRtStructError):
        rt_dvh_metrics(config, "ct.dcm", "dose.dcm", 1)
    with pytest.raises(NotDicomError):
        rt_dvh_metrics(config, "x.txt", "dose.dcm", 1)
    with pytest.raises(NotDicomError):
        rt_dvh_metrics(config, "struct.dcm", "x.txt", 1)


def test_paths_must_stay_inside_the_root(root: Path, outside: Path) -> None:
    struct_file(root, [cube()])
    dose_file(root, [10.0] * 6)
    write_rtdose(outside / "dose.dcm", np.ones((6, 10, 10)))
    config = Config.from_root(root)
    with pytest.raises(PathOutsideRootError):
        rt_dvh_metrics(config, "struct.dcm", str(outside / "dose.dcm"), 1)
    with pytest.raises(PathOutsideRootError):
        rt_dvh_metrics(config, str(outside / "dose.dcm"), "dose.dcm", 1)


def test_file_size_limit(root: Path) -> None:
    struct_file(root, [cube()])
    dose_file(root, [10.0] * 6)
    with pytest.raises(FileTooLargeError):
        run(root, config=Config.from_root(root, max_file_bytes=100))


# ------------------------------------------------------------------ work limits


def test_raster_work_limit(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    struct_file(root, [cube()])
    dose_file(root, [10.0] * 6)
    monkeypatch.setattr(rt_dvh, "MAX_RASTER_WORK", 10)
    with pytest.raises(WorkLimitError):
        run(root)


def test_contour_count_limit(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    struct_file(root, [cube()])
    dose_file(root, [10.0] * 6)
    monkeypatch.setattr(rt_dvh, "MAX_CONTOURS_PER_ROI", 3)
    with pytest.raises(WorkLimitError):
        run(root)


def test_work_limit_is_only_checked_for_slices_that_are_used(root: Path) -> None:
    """A structure far outside the grid costs no rasterisation work."""
    far = RoiSpec(1, "PTV", "PTV", "MANUAL", extrude(square(5000, 5000, 4000), Z_BOX))
    struct_file(root, [far])
    dose_file(root, [10.0] * 6)
    with pytest.raises(NoStructureVoxelsError):
        run(root)


# --------------------------------------------------------------------- security


def test_output_has_no_identifiers_uids_or_free_text(root: Path) -> None:
    spec = RoiSpec(1, FAKE_ROI_NAME, "PTV", "MANUAL", extrude(square(-1, -1, 10), Z_BOX))
    struct_file(root, [spec])
    dose_file(root, [10.0] * 6)
    result = run(root)
    serialized = json.dumps(result, allow_nan=False)
    for value in ALL_RT_IDENTIFYING_VALUES:
        assert value not in serialized
    assert result["name"] is None
    assert result["name_redacted"] is True
    assert "ContourData" not in serialized
    assert len(serialized) < 3_000


def test_operator_enabled_name_is_returned(root: Path) -> None:
    spec = RoiSpec(1, FAKE_ROI_NAME, "PTV", "MANUAL", extrude(square(-1, -1, 10), Z_BOX))
    struct_file(root, [spec])
    dose_file(root, [10.0] * 6)
    config = Config.from_root(root, extra_roi_names=frozenset({FAKE_ROI_NAME}))
    assert run(root, config=config)["name"] == FAKE_ROI_NAME


def test_error_messages_are_static(root: Path) -> None:
    struct_file(root, [cube()], name="SECRETNAME.dcm")
    dose_file(root, [10.0] * 6, name="SECRETDOSE.dcm")
    config = Config.from_root(root)
    with pytest.raises(StructureNotFoundError) as info:
        rt_dvh_metrics(config, "SECRETNAME.dcm", "SECRETDOSE.dcm", 99)
    assert "SECRET" not in str(info.value)
    with pytest.raises(NotRtStructError) as other:
        rt_dvh_metrics(config, "SECRETDOSE.dcm", "SECRETNAME.dcm", 1)
    assert "SECRET" not in str(other.value)


def test_method_notes_state_the_approximation(root: Path) -> None:
    struct_file(root, [cube()])
    dose_file(root, [10.0] * 6)
    notes = " ".join(run(root)["method_notes"])
    assert "approximate" in notes
    assert "not validated" in notes
