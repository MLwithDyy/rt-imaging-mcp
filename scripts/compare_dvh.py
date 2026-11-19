"""Compare ``rt_dvh_metrics`` with dicompyler-core on the same RTSTRUCT and RTDOSE files.

Run from the project environment (needs ``uv`` on PATH; dicompyler-core is installed
temporarily in an isolated environment):

    uv run python scripts/compare_dvh.py STRUCT.dcm DOSE.dcm ROI_NUMBER --percent 95 50 2 --gy 20

Only numbers are printed. dicompyler-core is an established open-source tool but it is not
ground truth: the two programs use different rules to decide which voxels belong to a
structure, so small differences are expected. Large differences deserve an explanation.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
REFERENCE = Path(__file__).with_name("dvh_reference_dicompyler.py")


def metrics_from_result(result: dict[str, Any]) -> dict[str, float]:
    """Flat metrics (the keys dicompyler-core results use) from an rt_dvh_metrics result."""
    # dicompyler-core computes the volume by counting dose-grid pixel centres inside each contour
    # plane and multiplying by the contour thickness, so it is a grid-sampled volume. Compare it
    # with our grid-sampled volume (not with the polygon-area volume).
    metrics: dict[str, float] = {
        "volume_cm3": result["volume_cm3"],
        "min": result["dose_gy"]["min"],
        "max": result["dose_gy"]["max"],
        "mean": result["dose_gy"]["mean"],
    }
    metrics.update(result["d_metrics_gy"])
    for key, value in result["v_metrics"].items():
        metrics[f"{key}_cm3"] = value["volume_cm3"]
    return metrics


def our_metrics(
    struct: Path, dose: Path, roi: int, percent: list[float], gy: list[float]
) -> dict[str, float]:
    sys.path.insert(0, str(REPO / "src"))
    from rt_imaging_mcp.config import Config
    from rt_imaging_mcp.tools.rt_dvh import rt_dvh_metrics

    root = Path(os.path.commonpath([struct.parent, dose.parent])).resolve()
    config = Config.from_root(root)
    result = rt_dvh_metrics(
        config,
        str(struct.resolve().relative_to(root)),
        str(dose.resolve().relative_to(root)),
        roi,
        percent,
        gy,
    )
    return metrics_from_result(result)


def reference_command(
    struct: Path, dose: Path, rois: list[int], percent: list[float], gy: list[float]
) -> list[str]:
    uv = shutil.which("uv")
    if uv is None:
        raise SystemExit("uv was not found on PATH; install it from https://docs.astral.sh/uv/")
    roi_arguments = [str(rois[0])] if len(rois) == 1 else ["--rois", *[str(r) for r in rois]]
    return [
        uv, "run", "--no-project", "--isolated", "--python", "3.12",
        "--with", "dicompyler-core", "--with", "pydicom<3", "--with", "numpy<2", "--with", "scipy",
        "python", str(REFERENCE), str(struct), str(dose), *roi_arguments,
        "--percent", *[f"{p:g}" for p in percent],
        "--gy", *[f"{t:g}" for t in gy],
    ]  # fmt: skip


def run_reference(
    struct: Path, dose: Path, rois: list[int], percent: list[float], gy: list[float]
) -> subprocess.CompletedProcess[str]:
    """Run the reference script. Callers decide what to print: stderr can contain file paths."""
    command = reference_command(struct, dose, rois, percent, gy)
    return subprocess.run(command, capture_output=True, text=True, check=False)


def reference_metrics(
    struct: Path, dose: Path, roi: int, percent: list[float], gy: list[float]
) -> dict[str, float]:
    completed = run_reference(struct, dose, [roi], percent, gy)
    if completed.returncode != 0:
        sys.stderr.write(completed.stderr[-2000:])
        raise SystemExit("the dicompyler-core reference run failed")
    return json.loads(completed.stdout.strip().splitlines()[-1])  # type: ignore[no-any-return]


def compare(
    ours: dict[str, float],
    reference: dict[str, float],
    tolerance_gy: float,
    tolerance_percent: float,
) -> list[dict[str, Any]]:
    """Row per metric: both values, the difference and whether it exceeds the tolerance.

    Dose metrics (Gy) use an absolute tolerance; volumes (cm3) use a relative one.
    """
    rows: list[dict[str, Any]] = []
    for key in ours:
        if key not in reference:
            continue
        a, b = ours[key], reference[key]
        difference = a - b
        if key.endswith("_cm3"):
            scale = max(abs(a), abs(b), 1e-12)
            exceeds = abs(difference) / scale * 100.0 > tolerance_percent
        else:
            exceeds = abs(difference) > tolerance_gy
        rows.append(
            {"metric": key, "ours": a, "reference": b, "difference": difference, "exceeds": exceeds}
        )
    return rows


def format_table(rows: list[dict[str, Any]]) -> str:
    lines = [f"{'metric':<14}{'ours':>12}{'dicompyler':>14}{'difference':>13}  flag"]
    for row in rows:
        flag = "DIFFERS" if row["exceeds"] else "ok"
        lines.append(
            f"{row['metric']:<14}{row['ours']:>12.4f}{row['reference']:>14.4f}"
            f"{row['difference']:>+13.4f}  {flag}"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("struct", type=Path)
    parser.add_argument("dose", type=Path)
    parser.add_argument("roi", type=int)
    parser.add_argument("--percent", type=float, nargs="*", default=[95.0, 50.0, 2.0])
    parser.add_argument("--gy", type=float, nargs="*", default=[20.0])
    parser.add_argument("--tolerance-gy", type=float, default=0.1)
    parser.add_argument("--tolerance-percent", type=float, default=2.0)
    parser.add_argument("--json", action="store_true", help="print the rows as JSON")
    args = parser.parse_args()

    ours = our_metrics(args.struct, args.dose, args.roi, args.percent, args.gy)
    reference = reference_metrics(args.struct, args.dose, args.roi, args.percent, args.gy)
    rows = compare(ours, reference, args.tolerance_gy, args.tolerance_percent)
    print(json.dumps(rows, indent=2) if args.json else format_table(rows))


if __name__ == "__main__":
    main()
