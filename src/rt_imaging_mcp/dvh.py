"""Dose-volume metrics from per-voxel doses (pure numpy, no file access).

Definitions (all voxels have equal volume):

* ``D(p)``: the highest dose ``d`` such that at least ``p`` percent of the structure volume
  receives a dose of ``d`` or more. ``D(100)`` is the minimum dose, ``D(2)`` is a near-maximum dose.
* ``V(t)``: the percentage and volume of the structure that receives at least ``t`` Gy.
  A small tolerance (1e-9 Gy) absorbs floating point error from the dose grid scaling.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

import numpy as np
from numpy.typing import NDArray

DOSE_TOLERANCE_GY = 1e-9
SLICE_TOLERANCE_MM = 1e-6


def nearest_slice_indices(
    dose_z: Sequence[float], contour_z: Sequence[float], thickness: float
) -> list[int | None]:
    """For each dose slice, the index of the contour slice whose slab contains it, or ``None``.

    Each contour slice stands for a slab of ``thickness`` mm centred on its z. A dose slice maps
    to the nearest contour slice if it lies inside that slab. Ties go to the lower z.
    ``contour_z`` must be ascending.
    """
    contour = np.asarray(contour_z, dtype=float)
    half = thickness / 2.0 + SLICE_TOLERANCE_MM
    result: list[int | None] = []
    for z in dose_z:
        distances = np.abs(contour - z)
        index = int(np.argmin(distances))
        result.append(index if distances[index] <= half else None)
    return result


def dose_at_volume(sorted_doses: NDArray[np.float64], percent: float) -> float:
    """``D(percent)`` for ascending ``sorted_doses``."""
    count = len(sorted_doses)
    needed = math.ceil(round(percent * count / 100.0, 9))
    needed = min(max(needed, 1), count)
    return float(sorted_doses[count - needed])


def volume_at_dose(doses: NDArray[np.float64], threshold_gy: float) -> int:
    """Number of voxels receiving at least ``threshold_gy``."""
    return int(np.count_nonzero(doses >= threshold_gy - DOSE_TOLERANCE_GY))


def format_number(value: float) -> str:
    """Compact key text: 95.0 -> '95', 2.5 -> '2.5'."""
    return f"{value:g}"


def dvh_metrics(
    doses: NDArray[np.float64],
    voxel_volume_mm3: float,
    percentages: Sequence[float],
    thresholds_gy: Sequence[float],
) -> dict[str, Any]:
    """Statistics, D(p) and V(t) for the voxel doses of one structure."""
    ordered = np.sort(doses)
    count = len(ordered)
    d_metrics = {f"D{format_number(p)}": round(dose_at_volume(ordered, p), 6) for p in percentages}
    v_metrics: dict[str, dict[str, float]] = {}
    for threshold in thresholds_gy:
        voxels = volume_at_dose(ordered, threshold)
        v_metrics[f"V{format_number(threshold)}Gy"] = {
            "percent": round(100.0 * voxels / count, 4),
            "volume_cm3": round(voxels * voxel_volume_mm3 / 1000.0, 6),
        }
    return {
        "dose_gy": {
            "min": round(float(ordered[0]), 6),
            "max": round(float(ordered[-1]), 6),
            "mean": round(float(ordered.mean(dtype=np.float64)), 6),
        },
        "d_metrics_gy": d_metrics,
        "v_metrics": v_metrics,
    }
