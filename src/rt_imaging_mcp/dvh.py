"""Dose-volume metrics from per-voxel doses (pure numpy, no file access).

Definitions (voxels carry a weight; the weight is 1 unless a dose slice is only partly inside the
structure or is shared between two contour slabs, see ``slice_contributions``):

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
WEIGHT_TOLERANCE = 1e-9


def slice_contributions(
    dose_z: Sequence[float],
    dose_thickness: float,
    contour_z: Sequence[float],
    contour_thickness: float,
) -> list[list[tuple[int, float]]]:
    """For each dose slice, the contour slices it overlaps and the weight of each.

    Each contour slice stands for a slab of ``contour_thickness`` mm centred on its z, and each
    dose slice for a slab of ``dose_thickness`` mm centred on its z. The weight of a contour
    slice for a dose slice is the fraction of the dose slab that overlaps the contour slab.
    A dose plane inside one slab gets ``[(index, 1.0)]``; a plane on the boundary between two
    slabs gets half of each; a plane on the outer boundary of the structure gets half of the
    outermost slab only; a plane outside gets ``[]``. Summed over all dose slices, every contour
    slab receives exactly its own thickness, so the structure volume equals the sum of the slabs
    however the planes fall. If slabs overlap (irregular contour spacing) the weights of one dose
    slice are scaled to add up to at most 1. ``contour_z`` must be ascending.
    """
    contour = np.asarray(contour_z, dtype=float)
    half_contour = contour_thickness / 2.0
    slab_low = contour - half_contour
    slab_high = contour + half_contour
    half_dose = dose_thickness / 2.0

    result: list[list[tuple[int, float]]] = []
    for z in dose_z:
        overlap = np.minimum(slab_high, z + half_dose) - np.maximum(slab_low, z - half_dose)
        weights = np.clip(overlap, 0.0, None) / dose_thickness
        total = float(weights.sum())
        if total > 1.0:
            weights = weights / total
        result.append(
            [
                (int(index), float(weights[index]))
                for index in np.flatnonzero(weights > SLICE_TOLERANCE_MM)
            ]
        )
    return result


def dose_at_volume(
    sorted_doses: NDArray[np.float64],
    percent: float,
    sorted_weights: NDArray[np.float64] | None = None,
) -> float:
    """``D(percent)`` for ascending ``sorted_doses`` (with the matching ``sorted_weights``)."""
    if sorted_weights is None:
        count = len(sorted_doses)
        needed = min(max(math.ceil(round(percent * count / 100.0, 9)), 1), count)
        return float(sorted_doses[count - needed])
    target = percent * float(sorted_weights.sum()) / 100.0
    from_the_top = np.cumsum(sorted_weights[::-1])
    index = int(np.searchsorted(from_the_top, target - WEIGHT_TOLERANCE, side="left"))
    index = min(index, len(sorted_doses) - 1)
    return float(sorted_doses[::-1][index])


def volume_at_dose(
    doses: NDArray[np.float64],
    threshold_gy: float,
    weights: NDArray[np.float64] | None = None,
) -> float:
    """Number of voxels (weighted when ``weights`` is given) receiving at least ``threshold_gy``."""
    above = doses >= threshold_gy - DOSE_TOLERANCE_GY
    if weights is None:
        return float(np.count_nonzero(above))
    return float(weights[above].sum())


def format_number(value: float) -> str:
    """Compact key text: 95.0 -> '95', 2.5 -> '2.5'."""
    return f"{value:g}"


def dvh_metrics(
    doses: NDArray[np.float64],
    voxel_volume_mm3: float,
    percentages: Sequence[float],
    thresholds_gy: Sequence[float],
    weights: NDArray[np.float64] | None = None,
) -> dict[str, Any]:
    """Statistics, D(p) and V(t) for the voxel doses of one structure."""
    order = np.argsort(doses, kind="stable")
    ordered = doses[order]
    ordered_weights = None if weights is None else weights[order]
    total = float(len(ordered)) if ordered_weights is None else float(ordered_weights.sum())
    d_metrics = {
        f"D{format_number(p)}": round(dose_at_volume(ordered, p, ordered_weights), 6)
        for p in percentages
    }
    v_metrics: dict[str, dict[str, float]] = {}
    for threshold in thresholds_gy:
        voxels = volume_at_dose(ordered, threshold, ordered_weights)
        v_metrics[f"V{format_number(threshold)}Gy"] = {
            "percent": round(100.0 * voxels / total, 4),
            "volume_cm3": round(voxels * voxel_volume_mm3 / 1000.0, 6),
        }
    mean = (
        np.average(ordered, weights=ordered_weights)
        if ordered_weights is not None
        else ordered.mean(dtype=np.float64)
    )
    return {
        "dose_gy": {
            "min": round(float(ordered[0]), 6),
            "max": round(float(ordered[-1]), 6),
            "mean": round(float(mean), 6),
        },
        "d_metrics_gy": d_metrics,
        "v_metrics": v_metrics,
    }
