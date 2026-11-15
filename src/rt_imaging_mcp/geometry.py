"""Small planar geometry helpers for RT structure contours (pure numpy)."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray

Polygon = NDArray[np.float64]  # shape (N, 2): x, y in millimetres


def polygon_area(polygon: Polygon) -> float:
    """Absolute area of a simple polygon (shoelace formula)."""
    x = polygon[:, 0]
    y = polygon[:, 1]
    return float(abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) / 2.0)


def point_in_polygon(point: tuple[float, float], polygon: Polygon) -> bool:
    """Even-odd ray casting test. Points exactly on an edge are not guaranteed either way."""
    px, py = point
    x = polygon[:, 0]
    y = polygon[:, 1]
    x_next = np.roll(x, -1)
    y_next = np.roll(y, -1)
    crosses = (y > py) != (y_next > py)
    with np.errstate(divide="ignore", invalid="ignore"):
        x_at_py = (x_next - x) * (py - y) / (y_next - y) + x
    return bool(np.count_nonzero(crosses & (px < x_at_py)) % 2 == 1)


def net_slice_area(polygons: Sequence[Polygon]) -> float:
    """Area enclosed by the contours of one slice, treating nested contours as holes.

    Containment depth decides the sign (even-odd rule): a contour inside one other contour
    is a hole, a contour inside that hole is material again, and so on. Each contour is
    probed with its first vertex, so contours that touch or share vertices are not handled.
    """
    total = 0.0
    for index, polygon in enumerate(polygons):
        probe = (float(polygon[0, 0]), float(polygon[0, 1]))
        depth = sum(
            1
            for other_index, other in enumerate(polygons)
            if other_index != index and point_in_polygon(probe, other)
        )
        total += polygon_area(polygon) * (1.0 if depth % 2 == 0 else -1.0)
    return max(total, 0.0)
