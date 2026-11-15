"""The synthetic generator itself must work, and must produce real DICOM files."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pydicom
import pytest

from tests.synthetic import (
    ALL_RT_IDENTIFYING_VALUES,
    FAKE_BEAM_NAME,
    FAKE_DOSE_REF_DESCRIPTION,
    FAKE_FOR_UID,
    FAKE_ID,
    FAKE_INSTITUTION,
    FAKE_MACHINE,
    FAKE_NAME,
    FAKE_OBS_LABEL,
    FAKE_PLAN_LABEL,
    FAKE_PLAN_NAME,
    FAKE_REFERENCED_UID,
    FAKE_REVIEWER,
    FAKE_ROI_NAME,
    FAKE_STRUCT_LABEL,
    IDENTIFYING_VALUES,
    BeamSpec,
    RoiSpec,
    write_dicom,
    write_rtdose,
    write_rtplan,
    write_rtstruct,
)


def test_written_file_has_dicom_magic_without_extension(tmp_path: Path) -> None:
    path = write_dicom(tmp_path / "noext")
    data = path.read_bytes()
    assert data[128:132] == b"DICM"


def test_written_file_round_trips(tmp_path: Path) -> None:
    path = write_dicom(tmp_path / "x.dcm")
    ds = pydicom.dcmread(path)
    assert ds.Modality == "CT"
    assert str(ds.PatientName) == FAKE_NAME


def test_builders_really_write_every_fake_identifier(tmp_path: Path) -> None:
    """Guards against vacuous leak tests: a misspelt DICOM keyword would silently write nothing."""
    files = {
        "ct": (write_dicom(tmp_path / "ct"), IDENTIFYING_VALUES),
        "struct": (
            write_rtstruct(tmp_path / "struct", [RoiSpec(1, FAKE_ROI_NAME)]),
            (FAKE_NAME, FAKE_ID, FAKE_STRUCT_LABEL, FAKE_ROI_NAME, FAKE_OBS_LABEL, FAKE_FOR_UID),
        ),
        "dose": (
            write_rtdose(tmp_path / "dose", np.ones((2, 2, 2))),
            (FAKE_NAME, FAKE_ID, FAKE_REFERENCED_UID, FAKE_FOR_UID),
        ),
        "plan": (
            write_rtplan(tmp_path / "plan", [BeamSpec(1)]),
            (
                FAKE_NAME,
                FAKE_ID,
                FAKE_INSTITUTION,
                FAKE_PLAN_LABEL,
                FAKE_PLAN_NAME,
                FAKE_REVIEWER,
                FAKE_MACHINE,
                FAKE_BEAM_NAME,
                FAKE_DOSE_REF_DESCRIPTION,
            ),
        ),
    }
    covered: set[str] = set()
    for label, (path, values) in files.items():
        data = path.read_bytes()
        for value in values:
            assert value.encode() in data, f"{label}: {value} was not written"
            covered.add(value)
    # Every value used by an "identifier must not appear" test is written by some builder.
    assert set(ALL_RT_IDENTIFYING_VALUES) <= covered


@pytest.mark.parametrize("value", ["SYNTHOBSLABEL", "SYNTHROI_Budi", "SYNTHSTRUCTLABEL"])
def test_rtstruct_builder_writes_roi_free_text(tmp_path: Path, value: str) -> None:
    path = write_rtstruct(tmp_path / "s", [RoiSpec(1, "SYNTHROI_Budi")])
    assert value.encode() in path.read_bytes()
