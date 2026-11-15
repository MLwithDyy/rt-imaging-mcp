"""NIfTI tool: rules R2, R3, R6."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rt_imaging_mcp.config import Config
from rt_imaging_mcp.security.errors import (
    FileTooLargeError,
    NotNiftiError,
    PathOutsideRootError,
)
from rt_imaging_mcp.tools.nifti import nifti_info
from tests.synthetic import FAKE_NIFTI_DESCRIP, write_nifti


def test_basic_info(root: Path) -> None:
    write_nifti(root / "vol")
    info = nifti_info(Config.from_root(root), "vol.nii")
    assert info["format"] == "NIfTI-1"
    assert info["shape"] == [4, 5, 6]
    assert info["ndim"] == 3
    assert info["voxel_count"] == 120
    assert info["data_type"] == "int16"
    assert info["voxel_size"] == [1.5, 1.5, 2.0]
    assert info["space_unit"] == "mm"
    assert info["orientation"] == "RAS"


def test_gzipped_file(root: Path) -> None:
    write_nifti(root / "vol", gz=True)
    assert nifti_info(Config.from_root(root), "vol.nii.gz")["shape"] == [4, 5, 6]


def test_four_dimensional(root: Path) -> None:
    write_nifti(root / "dyn", shape=(3, 3, 3, 2))
    info = nifti_info(Config.from_root(root), "dyn.nii")
    assert info["ndim"] == 4
    assert info["voxel_count"] == 54


def test_free_text_header_fields_never_returned(root: Path) -> None:
    write_nifti(root / "vol")
    serialized = json.dumps(nifti_info(Config.from_root(root), "vol.nii"))
    assert FAKE_NIFTI_DESCRIP not in serialized
    assert "SYNTHNAME" not in serialized
    assert "descrip" not in serialized


def test_output_is_json_serializable(root: Path) -> None:
    write_nifti(root / "vol")
    json.dumps(nifti_info(Config.from_root(root), "vol.nii"), allow_nan=False)


def test_non_nifti_file_rejected(root: Path) -> None:
    (root / "x.nii").write_bytes(b"not a nifti file at all" * 50)
    with pytest.raises(NotNiftiError):
        nifti_info(Config.from_root(root), "x.nii")


def test_dicom_file_is_not_nifti(root: Path) -> None:
    from tests.synthetic import write_dicom

    write_dicom(root / "scan.dcm")
    with pytest.raises(NotNiftiError):
        nifti_info(Config.from_root(root), "scan.dcm")


def test_too_large(root: Path) -> None:
    write_nifti(root / "vol")
    with pytest.raises(FileTooLargeError):
        nifti_info(Config.from_root(root, max_file_bytes=100), "vol.nii")


def test_outside_root_rejected(root: Path, outside: Path) -> None:
    write_nifti(outside / "vol")
    with pytest.raises(PathOutsideRootError):
        nifti_info(Config.from_root(root), str(outside / "vol.nii"))


def test_error_message_is_static(root: Path) -> None:
    (root / "SECRETNAME.nii").write_bytes(b"x" * 400)
    with pytest.raises(NotNiftiError) as info:
        nifti_info(Config.from_root(root), "SECRETNAME.nii")
    assert "SECRETNAME" not in str(info.value)
