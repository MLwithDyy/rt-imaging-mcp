"""rt_dose_summary and rt_plan_summary: rules R1, R2, R3, R6, R8, R11 and analytic checks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from rt_imaging_mcp.config import Config
from rt_imaging_mcp.security.errors import (
    FileTooLargeError,
    NotDicomError,
    NotRtDoseError,
    NotRtPlanError,
    PathOutsideRootError,
)
from rt_imaging_mcp.tools.rt_dose import rt_dose_summary
from rt_imaging_mcp.tools.rt_plan import MAX_BEAMS, rt_plan_summary
from tests.synthetic import (
    ALL_RT_IDENTIFYING_VALUES,
    BeamSpec,
    build_rtdose_dataset,
    write_dicom,
    write_rtdose,
    write_rtplan,
)

# ---------------------------------------------------------------- RTDOSE


def uniform(frames: int = 4, rows: int = 5, columns: int = 6, value: int = 2000) -> Any:
    return np.full((frames, rows, columns), value, dtype=np.uint32)


def test_uniform_dose_statistics(root: Path) -> None:
    write_rtdose(root / "dose.dcm", uniform(), scaling=0.001)
    summary = rt_dose_summary(Config.from_root(root), "dose.dcm")
    assert summary["max_dose"] == pytest.approx(2.0)
    assert summary["mean_dose"] == pytest.approx(2.0)
    assert summary["voxels_above_zero"] == 120
    assert summary["grid"] == {"frames": 4, "rows": 5, "columns": 6, "total_voxels": 120}
    assert summary["dose_units"] == "GY"
    assert summary["dose_type"] == "PHYSICAL"
    assert summary["dose_summation_type"] == "PLAN"
    assert summary["dose_grid_scaling"] == pytest.approx(0.001)


def test_gradient_dose_statistics(root: Path) -> None:
    raw = np.arange(120, dtype=np.uint32).reshape(4, 5, 6)
    write_rtdose(root / "dose.dcm", raw, scaling=0.01)
    summary = rt_dose_summary(Config.from_root(root), "dose.dcm")
    assert summary["max_dose"] == pytest.approx(1.19)  # 119 * 0.01
    assert summary["mean_dose"] == pytest.approx(0.595)  # 59.5 * 0.01
    assert summary["voxels_above_zero"] == 119


def test_voxel_size_and_uniform_spacing(root: Path) -> None:
    write_rtdose(root / "dose.dcm", uniform(), pixel_spacing=(2.5, 2.0))
    voxel = rt_dose_summary(Config.from_root(root), "dose.dcm")["voxel_size_mm"]
    assert voxel == {"row": 2.5, "column": 2.0, "slice": 3.0, "uniform_slice_spacing": True}


def test_non_uniform_slice_spacing_is_flagged(root: Path) -> None:
    write_rtdose(root / "dose.dcm", uniform(frames=4), slice_offsets=[0.0, 3.0, 7.0, 10.0])
    voxel = rt_dose_summary(Config.from_root(root), "dose.dcm")["voxel_size_mm"]
    assert voxel["slice"] == 3.0  # median of 3, 4, 3
    assert voxel["uniform_slice_spacing"] is False


def test_single_frame_has_no_slice_spacing(root: Path) -> None:
    write_rtdose(root / "dose.dcm", uniform(frames=1))
    voxel = rt_dose_summary(Config.from_root(root), "dose.dcm")["voxel_size_mm"]
    assert voxel["slice"] is None
    assert voxel["uniform_slice_spacing"] is None


def test_relative_dose_units(root: Path) -> None:
    write_rtdose(root / "dose.dcm", uniform(), DoseUnits="RELATIVE")
    assert rt_dose_summary(Config.from_root(root), "dose.dcm")["dose_units"] == "RELATIVE"


def test_unknown_code_strings_are_not_echoed(root: Path) -> None:
    write_rtdose(root / "dose.dcm", uniform(), DoseUnits="BUDI_UNITS", DoseType="SYNTHTYPE")
    summary = rt_dose_summary(Config.from_root(root), "dose.dcm")
    assert summary["dose_units"] is None
    assert summary["dose_type"] is None
    assert "BUDI" not in json.dumps(summary)


def test_dose_output_has_no_identifiers_positions_or_uids(root: Path) -> None:
    write_rtdose(root / "dose.dcm", uniform())
    serialized = json.dumps(rt_dose_summary(Config.from_root(root), "dose.dcm"))
    for value in ALL_RT_IDENTIFYING_VALUES:
        assert value not in serialized
    assert "-100" not in serialized  # grid position in patient space
    assert "PixelData" not in serialized
    assert len(serialized) < 2_000


def test_dose_output_is_json_serializable(root: Path) -> None:
    write_rtdose(root / "dose.dcm", uniform())
    json.dumps(rt_dose_summary(Config.from_root(root), "dose.dcm"), allow_nan=False)


def test_dose_rejects_other_modalities(root: Path) -> None:
    write_dicom(root / "ct.dcm")
    with pytest.raises(NotRtDoseError):
        rt_dose_summary(Config.from_root(root), "ct.dcm")


def test_dose_rejects_non_dicom(root: Path) -> None:
    (root / "x.txt").write_text("nope")
    with pytest.raises(NotDicomError):
        rt_dose_summary(Config.from_root(root), "x.txt")


def test_dose_rejects_truncated_pixel_data(root: Path) -> None:
    ds = build_rtdose_dataset(uniform())
    ds.PixelData = ds.PixelData[:-8]
    ds.save_as(root / "short.dcm", enforce_file_format=True)
    with pytest.raises(NotRtDoseError):
        rt_dose_summary(Config.from_root(root), "short.dcm")


def test_dose_rejects_missing_scaling(root: Path) -> None:
    ds = build_rtdose_dataset(uniform())
    del ds.DoseGridScaling
    ds.save_as(root / "noscale.dcm", enforce_file_format=True)
    with pytest.raises(NotRtDoseError):
        rt_dose_summary(Config.from_root(root), "noscale.dcm")


def test_dose_size_limit(root: Path) -> None:
    write_rtdose(root / "dose.dcm", uniform())
    with pytest.raises(FileTooLargeError):
        rt_dose_summary(Config.from_root(root, max_file_bytes=100), "dose.dcm")


def test_dose_outside_root(root: Path, outside: Path) -> None:
    write_rtdose(outside / "dose.dcm", uniform())
    with pytest.raises(PathOutsideRootError):
        rt_dose_summary(Config.from_root(root), str(outside / "dose.dcm"))


def test_dose_error_message_is_static(root: Path) -> None:
    write_dicom(root / "SECRETNAME.dcm")
    with pytest.raises(NotRtDoseError) as info:
        rt_dose_summary(Config.from_root(root), "SECRETNAME.dcm")
    assert "SECRETNAME" not in str(info.value)


# ---------------------------------------------------------------- RTPLAN


@pytest.fixture
def plan(root: Path) -> Path:
    beams = [
        BeamSpec(1, gantry=181.0, energy=6.0, dose=2.0, meterset=210.5),
        BeamSpec(2, gantry=270.0, energy=10.0, dose=1.8, meterset=180.0, couch=5.0),
        BeamSpec(
            3,
            radiation="ELECTRON",
            beam_type="DYNAMIC",
            energy=9.0,
            direction="CW",
            collimator=15.0,
            control_points=178,
            dose=0.4,
            meterset=90.0,
        ),
    ]
    return write_rtplan(root / "plan.dcm", beams, fractions=25, prescription_gy=50.0)


def test_plan_overview(root: Path, plan: Path) -> None:
    summary = rt_plan_summary(Config.from_root(root), "plan.dcm")
    assert summary["plan_geometry"] == "PATIENT"
    assert summary["approval_status"] == "APPROVED"
    assert summary["plan_intent"] == "CURATIVE"
    assert summary["fractions_planned"] == 25
    assert summary["fraction_group_count"] == 1
    assert summary["beam_count"] == 3
    assert summary["counts_by_radiation_type"] == {"ELECTRON": 1, "PHOTON": 2}
    assert summary["beams_truncated"] is False


def test_plan_beam_details(root: Path, plan: Path) -> None:
    beams = rt_plan_summary(Config.from_root(root), "plan.dcm")["beams"]
    first, second, third = beams
    assert first["beam_number"] == 1
    assert first["radiation_type"] == "PHOTON"
    assert first["beam_type"] == "STATIC"
    assert first["treatment_delivery_type"] == "TREATMENT"
    assert first["nominal_energy"] == 6.0
    assert first["gantry_angle_start"] == 181.0
    assert first["beam_dose_gy"] == pytest.approx(2.0)
    assert first["beam_meterset_mu"] == pytest.approx(210.5)
    assert second["couch_angle"] == 5.0
    assert third["radiation_type"] == "ELECTRON"
    assert third["beam_type"] == "DYNAMIC"
    assert third["control_point_count"] == 178
    assert third["gantry_rotation_direction"] == "CW"
    assert third["collimator_angle"] == 15.0


def test_plan_dose_references(root: Path, plan: Path) -> None:
    references = rt_plan_summary(Config.from_root(root), "plan.dcm")["dose_references"]
    assert references[0]["reference_type"] == "TARGET"
    assert references[0]["target_prescription_dose_gy"] == pytest.approx(50.0)
    assert references[1]["reference_type"] == "ORGAN_AT_RISK"
    assert references[1]["organ_at_risk_maximum_dose_gy"] == pytest.approx(45.0)


def test_plan_output_has_no_identifiers_or_free_text(root: Path, plan: Path) -> None:
    serialized = json.dumps(rt_plan_summary(Config.from_root(root), "plan.dcm"))
    for value in ALL_RT_IDENTIFYING_VALUES:
        assert value not in serialized
    json.loads(serialized)


def test_plan_unknown_codes_are_not_echoed(root: Path) -> None:
    beams = [BeamSpec(1, radiation="BUDI_RADIATION", beam_type="SYNTHTYPE", direction="SYNTHDIR")]
    write_rtplan(root / "plan.dcm", beams, ApprovalStatus="SYNTHSTATUS", PlanIntent="SYNTHINTENT")
    summary = rt_plan_summary(Config.from_root(root), "plan.dcm")
    assert summary["approval_status"] is None
    assert summary["plan_intent"] is None
    assert summary["beams"][0]["radiation_type"] is None
    assert summary["counts_by_radiation_type"] == {"UNKNOWN": 1}
    assert "BUDI" not in json.dumps(summary)
    assert "SYNTH" not in json.dumps(summary)


def test_plan_without_fraction_group(root: Path) -> None:
    write_rtplan(root / "plan.dcm", [BeamSpec(1)], fractions=None)
    summary = rt_plan_summary(Config.from_root(root), "plan.dcm")
    assert summary["fractions_planned"] is None
    assert summary["fraction_group_count"] == 0
    assert summary["beams"][0]["beam_dose_gy"] is None
    assert summary["beams"][0]["beam_meterset_mu"] is None


def test_plan_beam_count_is_bounded(root: Path) -> None:
    beams = [BeamSpec(number) for number in range(1, MAX_BEAMS + 6)]
    write_rtplan(root / "plan.dcm", beams)
    summary = rt_plan_summary(Config.from_root(root), "plan.dcm")
    assert summary["beams_truncated"] is True
    assert len(summary["beams"]) == MAX_BEAMS
    assert summary["beam_count"] == MAX_BEAMS + 5


def test_plan_rejects_other_modalities(root: Path) -> None:
    write_dicom(root / "ct.dcm")
    with pytest.raises(NotRtPlanError):
        rt_plan_summary(Config.from_root(root), "ct.dcm")


def test_plan_rejects_non_dicom(root: Path) -> None:
    (root / "x.txt").write_text("nope")
    with pytest.raises(NotDicomError):
        rt_plan_summary(Config.from_root(root), "x.txt")


def test_plan_size_limit(root: Path, plan: Path) -> None:
    with pytest.raises(FileTooLargeError):
        rt_plan_summary(Config.from_root(root, max_file_bytes=100), "plan.dcm")


def test_plan_outside_root(root: Path, outside: Path) -> None:
    write_rtplan(outside / "plan.dcm", [BeamSpec(1)])
    with pytest.raises(PathOutsideRootError):
        rt_plan_summary(Config.from_root(root), str(outside / "plan.dcm"))


def test_plan_error_message_is_static(root: Path) -> None:
    write_dicom(root / "SECRETNAME.dcm")
    with pytest.raises(NotRtPlanError) as info:
        rt_plan_summary(Config.from_root(root), "SECRETNAME.dcm")
    assert "SECRETNAME" not in str(info.value)
