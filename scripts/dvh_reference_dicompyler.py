"""Reference DVH numbers from dicompyler-core, printed as one JSON line.

Run this in an isolated environment, not in the project environment: dicompyler-core 0.5.x
needs pydicom < 3 and numpy < 2, while this project needs pydicom >= 3. ``compare_dvh.py``
does that for you with ``uv run --isolated``. It prints numbers only, never names or IDs.

    uv run --no-project --isolated --with dicompyler-core --with "pydicom<3" \\
        --with "numpy<2" --with scipy python scripts/dvh_reference_dicompyler.py \\
        STRUCT.dcm DOSE.dcm ROI_NUMBER --percent 95 50 2 --gy 20
"""

from __future__ import annotations

import argparse
import json
import warnings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("struct")
    parser.add_argument("dose")
    parser.add_argument("roi", type=int)
    parser.add_argument("--percent", type=float, nargs="*", default=[95.0, 50.0, 2.0])
    parser.add_argument("--gy", type=float, nargs="*", default=[20.0])
    args = parser.parse_args()

    warnings.simplefilter("ignore")
    from dicompylercore import dvhcalc

    dvh = dvhcalc.get_dvh(args.struct, args.dose, args.roi)
    result: dict[str, float] = {
        "volume_cm3": float(dvh.volume),
        "min": float(dvh.min),
        "max": float(dvh.max),
        "mean": float(dvh.mean),
    }
    for percent in args.percent:
        result[f"D{percent:g}"] = float(dvh.statistic(f"D{percent:g}").value)
    for threshold in args.gy:
        result[f"V{threshold:g}Gy_cm3"] = float(dvh.volume_constraint(threshold, "Gy").value)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
