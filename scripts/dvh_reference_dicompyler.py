"""Reference DVH numbers from dicompyler-core, printed as one JSON line.

Run this in an isolated environment, not in the project environment: dicompyler-core 0.5.x
needs pydicom < 3 and numpy < 2, while this project needs pydicom >= 3. ``compare_dvh.py``
and ``validate_collection.py`` do that for you with ``uv run --isolated``. It prints numbers
only, never names, IDs or paths.

One structure (prints a flat object):

    uv run --no-project --isolated --with dicompyler-core --with "pydicom<3" \\
        --with "numpy<2" --with scipy python scripts/dvh_reference_dicompyler.py \\
        STRUCT.dcm DOSE.dcm ROI_NUMBER --percent 95 50 2 --gy 20

Several structures (prints an object keyed by ROI number; a failing structure maps to
``{"error": "<ExceptionName>"}``): replace ROI_NUMBER by ``--rois 1 2 3``.
"""

from __future__ import annotations

import argparse
import json
import warnings
from typing import Any


def structure_metrics(
    structure: str, dose: str, roi: int, percent: list[float], gy: list[float]
) -> dict[str, float]:
    from dicompylercore import dvhcalc

    dvh = dvhcalc.get_dvh(structure, dose, roi)
    result: dict[str, float] = {
        "volume_cm3": float(dvh.volume),
        "min": float(dvh.min),
        "max": float(dvh.max),
        "mean": float(dvh.mean),
    }
    for value in percent:
        result[f"D{value:g}"] = float(dvh.statistic(f"D{value:g}").value)
    for threshold in gy:
        result[f"V{threshold:g}Gy_cm3"] = float(dvh.volume_constraint(threshold, "Gy").value)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("struct")
    parser.add_argument("dose")
    parser.add_argument("roi", type=int, nargs="?")
    parser.add_argument("--rois", type=int, nargs="+")
    parser.add_argument("--percent", type=float, nargs="*", default=[95.0, 50.0, 2.0])
    parser.add_argument("--gy", type=float, nargs="*", default=[20.0])
    args = parser.parse_args()
    if (args.roi is None) == (args.rois is None):
        parser.error("give either ROI_NUMBER or --rois")

    warnings.simplefilter("ignore")
    if args.rois is None:
        print(
            json.dumps(structure_metrics(args.struct, args.dose, args.roi, args.percent, args.gy))
        )
        return

    results: dict[str, Any] = {}
    for roi in args.rois:
        try:
            results[str(roi)] = structure_metrics(
                args.struct, args.dose, roi, args.percent, args.gy
            )
        except Exception as error:  # report the kind only: messages may contain file paths
            results[str(roi)] = {"error": type(error).__name__}
    print(json.dumps(results))


if __name__ == "__main__":
    main()
