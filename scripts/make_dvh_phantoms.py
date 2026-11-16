"""Write the synthetic RT phantoms used to compare dose-volume metrics.

    uv run python scripts/make_dvh_phantoms.py OUTPUT_DIR

Each phantom folder holds ``struct.dcm`` and ``dose.dcm`` (structure number 1). The dose
rises smoothly with row, column and slice, so D(p) is well defined. All data is generated
here; nothing medical is read or stored.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.synthetic import RoiSpec, extrude, square, write_rtdose, write_rtstruct  # noqa: E402

SCALING = 0.001
ALIGNED = [0.0, 2.0, 4.0, 6.0, 8.0]


def smooth_dose(frames: int, rows: int = 10, columns: int = 10) -> np.ndarray:
    frame, row, column = np.meshgrid(
        np.arange(frames), np.arange(rows), np.arange(columns), indexing="ij"
    )
    gray = 10 + 0.1 * row + 0.15 * column + 0.2 * frame
    return np.round(gray / SCALING).astype(np.uint32)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("output", type=Path)
    output = parser.parse_args().output

    hexagon = [(9 + 7 * np.cos(a), 9 + 6 * np.sin(a)) for a in np.linspace(0, 2 * np.pi, 7)[:-1]]
    outer, hole = square(-1, -1, 12), square(3, 3, 4)
    dose_slices = [0.0, 2.0, 4.0, 6.0, 8.0, 10.0]
    phantoms = {
        "aligned_cube": (
            [RoiSpec(1, "PTV", "PTV", "MANUAL", extrude(square(-1, -1, 10), ALIGNED))],
            dose_slices,
        ),
        "aligned_hexagon": (
            [RoiSpec(1, "PTV", "PTV", "MANUAL", extrude(hexagon, ALIGNED))],
            dose_slices,
        ),
        "aligned_with_hole": (
            [
                RoiSpec(
                    1, "Rectum", "ORGAN", "MANUAL", [(z, p) for z in ALIGNED for p in (outer, hole)]
                )
            ],
            dose_slices,
        ),
        "misaligned_cube": (
            [RoiSpec(1, "PTV", "PTV", "MANUAL", extrude(square(-1, -1, 10), [0, 3, 6, 9]))],
            [0.0, 2.0, 4.0, 6.0, 8.0, 10.0, 12.0],
        ),
    }
    for name, (rois, offsets) in phantoms.items():
        folder = output / name
        folder.mkdir(parents=True, exist_ok=True)
        write_rtstruct(folder / "struct.dcm", rois)
        write_rtdose(
            folder / "dose.dcm",
            smooth_dose(len(offsets)),
            scaling=SCALING,
            pixel_spacing=(2.0, 2.0),
            slice_offsets=offsets,
            origin=(0.0, 0.0, 0.0),
        )
        print(f"wrote {folder}")


if __name__ == "__main__":
    main()
