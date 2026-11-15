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


def _crossing_edges(polygon: Polygon) -> tuple[NDArray[np.float64], ...]:
    """Edge end points (x1, y1, x2, y2) of all non-horizontal edges."""
    x1, y1 = polygon[:, 0], polygon[:, 1]
    x2, y2 = np.roll(x1, -1), np.roll(y1, -1)
    keep = y1 != y2
    return x1[keep], y1[keep], x2[keep], y2[keep]


def _bounds(polygon: Polygon) -> tuple[float, float, float, float]:
    """Bounding box (min_x, max_x, min_y, max_y)."""
    low = polygon.min(axis=0)
    high = polygon.max(axis=0)
    return float(low[0]), float(high[0]), float(low[1]), float(high[1])


def _index_range(axis: NDArray[np.float64], low: float, high: float) -> tuple[int, int]:
    """Half-open index range of the ascending ``axis`` values inside [low, high]."""
    start = int(np.searchsorted(axis, low, side="left"))
    stop = int(np.searchsorted(axis, high, side="right"))
    return start, max(start, stop)


def polygon_work(xs: NDArray[np.float64], ys: NDArray[np.float64], polygon: Polygon) -> int:
    """Upper bound of the work ``polygon_mask`` does: bounding-box cells times crossing edges."""
    min_x, max_x, min_y, max_y = _bounds(polygon)
    c0, c1 = _index_range(xs, min_x, max_x)
    r0, r1 = _index_range(ys, min_y, max_y)
    return (c1 - c0) * (r1 - r0) * len(_crossing_edges(polygon)[0])


def polygon_mask(
    xs: NDArray[np.float64], ys: NDArray[np.float64], polygon: Polygon
) -> NDArray[np.bool_]:
    """Mask of grid cell centres inside ``polygon``, shape (len(ys), len(xs)).

    ``xs`` (columns) and ``ys`` (rows) must be ascending. Uses the even-odd rule with the same
    edge convention as ``point_in_polygon``: a centre exactly on a vertical edge counts as
    inside on its left side only.
    """
    mask = np.zeros((ys.size, xs.size), dtype=bool)
    min_x, max_x, min_y, max_y = _bounds(polygon)
    c0, c1 = _index_range(xs, min_x, max_x)
    r0, r1 = _index_range(ys, min_y, max_y)
    if c1 <= c0 or r1 <= r0:
        return mask

    grid_x, grid_y = np.meshgrid(xs[c0:c1], ys[r0:r1])
    px, py = grid_x.ravel(), grid_y.ravel()
    inside = np.zeros(px.shape, dtype=bool)
    x1, y1, x2, y2 = _crossing_edges(polygon)
    for ax, ay, bx, by in zip(x1, y1, x2, y2, strict=True):
        crosses = (ay > py) != (by > py)
        x_at_py = (bx - ax) * (py - ay) / (by - ay) + ax
        inside ^= crosses & (px < x_at_py)
    mask[r0:r1, c0:c1] = inside.reshape(grid_x.shape)
    return mask
