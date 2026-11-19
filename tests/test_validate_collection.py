"""scripts/validate_collection.py: discovery, pairing, aggregation and anonymous output.

The dicompyler-core run is replaced by a fake that answers with our own numbers, so these
tests need neither uv nor network access.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest

from tests.synthetic import (
    RoiSpec,
    extrude,
    square,
    write_dicom,
    write_rtdose,
    write_rtstruct,
)

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_collection.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("validate_collection", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["validate_collection"] = module
    spec.loader.exec_module(module)
    return module


validate = _load()
Z = [0.0, 2.0, 4.0, 6.0, 8.0]
ROIS = [
    RoiSpec(1, "PTV", "PTV", "MANUAL", extrude(square(-1, -1, 10), Z)),
    RoiSpec(2, "Bladder", "ORGAN", "MANUAL", extrude(square(1, 1, 8), Z)),
    RoiSpec(3, "SYNTHROI_Budi", "ORGAN", "MANUAL", extrude(square(-1, -1, 10), Z)),
    RoiSpec(4, "Tiny", "ORGAN", "MANUAL", extrude(square(-1, -1, 1), Z)),
]


def make_case(
    root: Path, name: str, *, struct_kwargs: dict[str, Any] | None = None, **dose_kwargs: Any
) -> Path:
    folder = root / name
    for sub in ("CT", "RS", "RD"):
        (folder / sub).mkdir(parents=True)
    write_dicom(folder / "CT" / "slice")
    write_rtstruct(folder / "RS" / "struct.dcm", ROIS, **(struct_kwargs or {}))
    frame, row, column = np.meshgrid(np.arange(6), np.arange(10), np.arange(10), indexing="ij")
    raw = np.round((10 + 0.1 * row + 0.15 * column + 0.2 * frame) / 0.001).astype(np.uint32)
    write_rtdose(
        folder / "RD" / "dose.dcm",
        raw,
        scaling=0.001,
        pixel_spacing=(2.0, 2.0),
        slice_offsets=[0, 2, 4, 6, 8, 10],
        origin=(0.0, 0.0, 0.0),
        **dose_kwargs,
    )
    return folder


@pytest.fixture
def tree(root: Path) -> Path:
    make_case(root, "PatientA_Budi")
    make_case(root, "PatientB_Siti", struct_kwargs={"frame_of_reference_uid": "1.2.826.0.9.9"})
    make_case(root, "PatientC", DoseUnits="RELATIVE")
    (root / "PatientD").mkdir()
    write_dicom(root / "PatientD" / "only_ct")
    return root


@pytest.fixture
def fake_reference(monkeypatch: pytest.MonkeyPatch, tree: Path) -> None:
    from rt_imaging_mcp.config import Config
    from rt_imaging_mcp.tools.rt_dvh import rt_dvh_metrics

    def fake(
        struct: Path, dose: Path, rois: list[int], percent: list[float], gy: list[float]
    ) -> subprocess.CompletedProcess[str]:
        config = Config.from_root(tree)
        results = {
            str(roi): validate.metrics_from_result(
                rt_dvh_metrics(
                    config,
                    str(struct.relative_to(tree)),
                    str(dose.relative_to(tree)),
                    roi,
                    percent,
                    gy,
                )
            )
            for roi in rois
        }
        payload = results[str(rois[0])] if len(rois) == 1 else results
        return subprocess.CompletedProcess([], 0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(validate, "run_reference", fake)


# ----------------------------------------------------------------- discovery


def test_read_rt_file_recognises_only_rtstruct_and_rtdose(tree: Path) -> None:
    case = tree / "PatientA_Budi"
    assert validate.read_rt_file(case / "RS" / "struct.dcm").modality == "RTSTRUCT"
    assert validate.read_rt_file(case / "RD" / "dose.dcm").modality == "RTDOSE"
    assert validate.read_rt_file(case / "CT" / "slice") is None
    (case / "junk.txt").write_text("not dicom")
    assert validate.read_rt_file(case / "junk.txt") is None


def test_discover_keeps_only_cases_with_structure_and_dose(tree: Path) -> None:
    cases = validate.discover(tree, case_depth=1, max_cases=None)
    assert [case.label for case in cases] == ["case_001", "case_002", "case_003"]
    assert all(len(case.structs) == 1 and len(case.doses) == 1 for case in cases)


def test_discover_respects_max_cases_and_depth(tree: Path, root: Path) -> None:
    assert len(validate.discover(tree, 1, max_cases=2)) == 2
    nested = root / "COLLECTION"
    nested.mkdir()
    make_case(nested, "P1")
    make_case(nested, "P2")
    assert len(validate.discover(nested, 1, None)) == 2
    # At depth 2 the cases are the folders inside COLLECTION; the PatientA..D folders only hold
    # CT, RS or RD sub-folders, none of which has both an RTSTRUCT and an RTDOSE.
    deeper = validate.discover(root, 2, None)
    assert [case.label for case in deeper] == ["case_001", "case_002"]


def test_pairing_requires_a_shared_frame_of_reference(tree: Path) -> None:
    cases = {case.label: case for case in validate.discover(tree, 1, None)}
    matching, mismatched = validate.pair_files(cases["case_001"], max_pairs=3)
    assert len(matching) == 1 and mismatched == 0
    matching, mismatched = validate.pair_files(cases["case_002"], max_pairs=3)
    assert matching == [] and mismatched == 1


def test_plan_doses_are_preferred_over_beam_doses() -> None:
    struct = validate.RtFile(Path("s"), "RTSTRUCT", "F", "")
    beam = validate.RtFile(Path("b"), "RTDOSE", "F", "BEAM")
    plan = validate.RtFile(Path("p"), "RTDOSE", "F", "PLAN")
    case = validate.Case("case_001", [struct], [beam, plan])
    assert validate.pair_files(case, 5)[0] == [(struct, plan)]


def test_structure_selection_uses_standard_names_and_minimum_volume() -> None:
    summary = {
        "rois": [
            {"roi_number": 1, "name": "PTV", "approx_volume_cm3": 5.0},
            {"roi_number": 2, "name": None, "approx_volume_cm3": 50.0},
            {"roi_number": 3, "name": "Bladder", "approx_volume_cm3": 0.2},
            {"roi_number": 4, "name": "Rectum", "approx_volume_cm3": None},
            {"roi_number": 5, "name": "Heart", "approx_volume_cm3": 9.0},
        ]
    }
    chosen = validate.select_structures(summary, max_rois=5, min_volume_cm3=1.0)
    assert [roi["roi_number"] for roi in chosen] == [1, 5]
    assert len(validate.select_structures(summary, max_rois=1, min_volume_cm3=1.0)) == 1


def test_redacted_structures_can_be_included_on_request() -> None:
    summary = {
        "rois": [
            {"roi_number": 1, "name": "PTV", "approx_volume_cm3": 5.0},
            {"roi_number": 2, "name": None, "approx_volume_cm3": 50.0},
            {"roi_number": 3, "name": None, "approx_volume_cm3": 0.2},
        ]
    }
    chosen = validate.select_structures(summary, 10, 1.0, include_redacted=True)
    assert [roi["roi_number"] for roi in chosen] == [1, 2]


# ---------------------------------------------------------------- aggregation


def test_summary_statistics() -> None:
    rows = [
        {"comparison": [{"metric": "D95", "difference": 0.02, "exceeds": False}]},
        {"comparison": [{"metric": "D95", "difference": -0.20, "exceeds": True}]},
        {"comparison": [{"metric": "D95", "difference": 0.04, "exceeds": False}]},
    ]
    summary = validate.summarize(rows)
    assert summary["compared_structures"] == 3
    assert summary["metrics"]["D95"] == {
        "n": 3,
        "median_abs_difference": 0.04,
        "max_abs_difference": 0.2,
        "exceeding_tolerance": 1,
    }


def test_summary_of_nothing() -> None:
    assert validate.summarize([]) == {"compared_structures": 0, "metrics": {}}


# --------------------------------------------------- the whole script, anonymised


def run_main(monkeypatch: pytest.MonkeyPatch, tree: Path, *extra: str) -> None:
    arguments = [
        "validate_collection.py",
        str(tree),
        "--min-volume-cm3",
        "0.5",
        "--gy",
        "11",
        *extra,
    ]
    monkeypatch.setattr(sys, "argv", arguments)
    validate.main()


def test_output_is_anonymous_and_reports_skips_and_refusals(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tree: Path,
    fake_reference: None,
) -> None:
    run_main(monkeypatch, tree)
    output = capsys.readouterr().out

    for forbidden in ("Patient", "Budi", "Siti", "SYNTH", str(tree), "struct.dcm", "dose.dcm"):
        assert forbidden not in output
    assert "cases found: 3, structure/dose pairs run: 2" in output
    assert "pairs skipped (frame of reference missing or different): 1" in output
    assert "case_001" in output
    assert "PTV" in output and "Bladder" in output
    assert "Tiny" not in output  # below the minimum volume, and not a standard name anyway
    assert "dose grid orientation, spacing or units are not supported" in output


def test_identical_results_show_no_differences(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tree: Path,
    fake_reference: None,
    tmp_path: Path,
) -> None:
    target = tmp_path / "out.json"
    run_main(monkeypatch, tree, "--json-out", str(target))
    capsys.readouterr()
    payload = json.loads(target.read_text(encoding="utf-8"))

    assert payload["summary"]["compared_structures"] == 2  # PTV and Bladder of the one valid case
    for values in payload["summary"]["metrics"].values():
        assert values["max_abs_difference"] == 0
        assert values["exceeding_tolerance"] == 0
    text = json.dumps(payload)
    for forbidden in ("Patient", "Budi", "Siti", "SYNTH", str(tree)):
        assert forbidden not in text
    assert (
        sum(payload["refusals"].values()) == 2
    )  # PTV and Bladder refused on the relative dose case


def test_a_failing_reference_run_is_counted_without_printing_its_stderr(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tree: Path,
) -> None:
    def failing(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            [], 1, stdout="", stderr=f"cannot read {tree}/PatientA_Budi"
        )

    monkeypatch.setattr(validate, "run_reference", failing)
    run_main(monkeypatch, tree)
    output = capsys.readouterr().out
    assert "dicompyler-core: reference run failed" in output
    assert "Budi" not in output


def test_no_cases_is_an_error(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    monkeypatch.setattr(sys, "argv", ["validate_collection.py", str(root)])
    with pytest.raises(SystemExit):
        validate.main()


def test_include_redacted_reports_them_by_number_only(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tree: Path,
    fake_reference: None,
) -> None:
    run_main(monkeypatch, tree, "--include-redacted")
    output = capsys.readouterr().out
    assert "(redacted)" in output
    assert "SYNTH" not in output and "Budi" not in output


def test_enabled_names_are_printed_and_selected(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tree: Path,
    fake_reference: None,
) -> None:
    run_main(monkeypatch, tree, "--enable-roi-name", "SYNTHROI_Budi")
    output = capsys.readouterr().out
    assert "SYNTHROI_Budi" in output  # the operator asked for it explicitly
    assert "Patient" not in output and str(tree) not in output


def test_debug_reference_prints_stderr_only_when_asked(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tree: Path,
) -> None:
    def failing(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], 1, stdout="", stderr="REFERENCE-STDERR-MARKER")

    monkeypatch.setattr(validate, "run_reference", failing)
    run_main(monkeypatch, tree)
    assert "REFERENCE-STDERR-MARKER" not in capsys.readouterr().err
    run_main(monkeypatch, tree, "--debug-reference")
    assert "REFERENCE-STDERR-MARKER" in capsys.readouterr().err


def test_volume_classes() -> None:
    edges = [20.0, 200.0]
    assert validate.volume_class(5.0, edges) == "<20 cm3"
    assert validate.volume_class(20.0, edges) == "20-200 cm3"
    assert validate.volume_class(199.9, edges) == "20-200 cm3"
    assert validate.volume_class(200.0, edges) == ">=200 cm3"
    assert validate.volume_class(3000.0, edges) == ">=200 cm3"


def test_summary_by_volume_class() -> None:
    def row(volume: float, difference: float) -> dict[str, Any]:
        return {
            "volume_cm3": volume,
            "comparison": [{"metric": "D95", "difference": difference, "exceeds": False}],
        }

    rows = [row(5.0, 0.5), row(8.0, 0.1), row(500.0, 0.01)]
    grouped = validate.summarize_by_volume(rows, [20.0, 200.0])
    assert sorted(grouped) == ["<20 cm3", ">=200 cm3"]
    assert grouped["<20 cm3"]["compared_structures"] == 2
    assert grouped["<20 cm3"]["metrics"]["D95"]["max_abs_difference"] == 0.5
    assert grouped[">=200 cm3"]["metrics"]["D95"]["median_abs_difference"] == 0.01


def test_output_lists_voxel_size_and_summaries_by_size(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tree: Path,
    fake_reference: None,
) -> None:
    run_main(monkeypatch, tree)
    output = capsys.readouterr().out
    assert "voxel mm" in output and "2x2x2" in output
    assert "structure volume" in output
