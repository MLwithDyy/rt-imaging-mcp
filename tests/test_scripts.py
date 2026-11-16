"""The DVH comparison script: its comparison and formatting logic (no dicompyler-core needed)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "compare_dvh.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("compare_dvh", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


compare_dvh = _load()


def test_identical_results_do_not_differ() -> None:
    metrics = {"volume_cm3": 1.0, "mean": 11.0, "D95": 10.3, "V11Gy_cm3": 0.4}
    rows = compare_dvh.compare(metrics, dict(metrics), 0.1, 2.0)
    assert [row["metric"] for row in rows] == ["volume_cm3", "mean", "D95", "V11Gy_cm3"]
    assert not any(row["exceeds"] for row in rows)


def test_dose_metrics_use_an_absolute_tolerance_in_gy() -> None:
    rows = compare_dvh.compare({"D95": 10.30}, {"D95": 10.15}, 0.1, 2.0)
    assert rows[0]["exceeds"] is True
    assert rows[0]["difference"] == 10.30 - 10.15
    assert not compare_dvh.compare({"D95": 10.30}, {"D95": 10.22}, 0.1, 2.0)[0]["exceeds"]


def test_volumes_use_a_relative_tolerance_in_percent() -> None:
    assert compare_dvh.compare({"volume_cm3": 1.00}, {"volume_cm3": 1.03}, 0.1, 2.0)[0]["exceeds"]
    assert not compare_dvh.compare({"volume_cm3": 1.00}, {"volume_cm3": 1.01}, 0.1, 2.0)[0][
        "exceeds"
    ]
    assert compare_dvh.compare({"V11Gy_cm3": 0.632}, {"V11Gy_cm3": 0.588}, 0.1, 2.0)[0]["exceeds"]


def test_metrics_missing_on_one_side_are_skipped() -> None:
    rows = compare_dvh.compare({"D95": 1.0, "D2": 2.0}, {"D95": 1.0}, 0.1, 2.0)
    assert [row["metric"] for row in rows] == ["D95"]


def test_zero_volumes_do_not_divide_by_zero() -> None:
    rows = compare_dvh.compare({"V20Gy_cm3": 0.0}, {"V20Gy_cm3": 0.0}, 0.1, 2.0)
    assert rows[0]["exceeds"] is False


def test_table_marks_differences() -> None:
    rows = compare_dvh.compare({"mean": 10.0, "D95": 9.0}, {"mean": 10.01, "D95": 8.0}, 0.1, 2.0)
    table = compare_dvh.format_table(rows)
    assert "DIFFERS" in table
    assert "ok" in table
    assert "dicompyler" in table.splitlines()[0]
