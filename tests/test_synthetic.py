"""The synthetic generator itself must work, and must produce real DICOM files."""

from __future__ import annotations

from pathlib import Path

import pydicom

from tests.synthetic import FAKE_NAME, write_dicom


def test_written_file_has_dicom_magic_without_extension(tmp_path: Path) -> None:
    path = write_dicom(tmp_path / "noext")
    data = path.read_bytes()
    assert data[128:132] == b"DICM"


def test_written_file_round_trips(tmp_path: Path) -> None:
    path = write_dicom(tmp_path / "x.dcm")
    ds = pydicom.dcmread(path)
    assert ds.Modality == "CT"
    assert str(ds.PatientName) == FAKE_NAME
