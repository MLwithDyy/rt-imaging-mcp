"""Rule R9: no patient data in the repository.

Tests the pre-commit guard script, the hook configuration and the .gitignore patterns.
All files are generated at run time; nothing medical is stored in the repository.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

from tests.synthetic import write_dicom, write_nifti

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "check_no_medical_images.py"


def _load_guard() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_no_medical_images", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = _load_guard()


@pytest.mark.parametrize(
    "name",
    ["scan.dcm", "SCAN.DCM", "image.dicom", "vol.nii", "vol.nii.gz", "a.mha", "a.mhd", "a.nrrd"],
)
def test_blocks_medical_image_extensions(tmp_path: Path, name: str) -> None:
    path = tmp_path / name
    path.write_bytes(b"x")
    assert guard.blocked_reason(path) is not None


def test_blocks_dicomdir(tmp_path: Path) -> None:
    path = tmp_path / "DICOMDIR"
    path.write_bytes(b"x")
    assert guard.blocked_reason(path) is not None


def test_blocks_dicom_without_extension(tmp_path: Path) -> None:
    path = write_dicom(tmp_path / "IM0001")
    assert guard.blocked_reason(path) == "DICOM magic bytes found"


def test_blocks_real_dicom_and_nifti_writers_output(tmp_path: Path) -> None:
    assert guard.blocked_reason(write_dicom(tmp_path / "x.dcm")) is not None
    assert guard.blocked_reason(write_nifti(tmp_path / "v")) is not None
    assert guard.blocked_reason(write_nifti(tmp_path / "w", gz=True)) is not None


@pytest.mark.parametrize("name", ["README.md", "notes.txt", "module.py", "data.json"])
def test_allows_ordinary_files(tmp_path: Path, name: str) -> None:
    path = tmp_path / name
    path.write_text("hello")
    assert guard.blocked_reason(path) is None


def test_missing_file_is_not_blocked_and_does_not_crash(tmp_path: Path) -> None:
    assert guard.blocked_reason(tmp_path / "does-not-exist") is None


def test_main_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    safe = tmp_path / "ok.txt"
    safe.write_text("ok")
    bad = write_dicom(tmp_path / "IM0001")

    assert guard.main([str(safe)]) == 0
    assert guard.main([str(safe), str(bad)]) == 1
    err = capsys.readouterr().err
    assert "BLOCKED" in err
    assert "IM0001" in err


def test_gitignore_blocks_medical_data_patterns() -> None:
    lines = {
        line.strip()
        for line in (REPO / ".gitignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }
    for pattern in ("*.dcm", "*.nii", "*.nii.gz", "DICOMDIR", "data/", "private/"):
        assert pattern in lines


def test_precommit_config_runs_the_guard_in_a_python_env() -> None:
    config = (REPO / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    assert "scripts/check_no_medical_images.py" in config
    # "language: system" would depend on a "python" executable being on PATH.
    assert "language: python" in config
    assert "language: system" not in config


def test_repository_contains_no_medical_image_files() -> None:
    """Scan the working tree (outside virtual environments and caches) with the guard itself."""
    ignored = {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
    }
    offenders = [
        str(path.relative_to(REPO))
        for path in REPO.rglob("*")
        if path.is_file()
        and not ignored.intersection(path.relative_to(REPO).parts)
        and guard.blocked_reason(path) is not None
    ]
    assert offenders == []
