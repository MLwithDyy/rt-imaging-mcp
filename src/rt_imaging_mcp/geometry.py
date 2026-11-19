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


def _row_spans(
    ys: NDArray[np.float64],
    x1: NDArray[np.float64],
    y1: NDArray[np.float64],
    y2: NDArray[np.float64],
) -> tuple[NDArray[np.intp], NDArray[np.intp], NDArray[np.intp]]:
    """For every edge, the rows whose centre line it crosses.

    An edge crosses a row line ``y`` when ``min(y1, y2) <= y < max(y1, y2)``, the half-open rule
    of the ray casting test. Returns ``(first_row, row_count, edge_of_each_crossing)``.
    """
    low = np.minimum(y1, y2)
    high = np.maximum(y1, y2)
    first = np.searchsorted(ys, low, side="left")
    last = np.searchsorted(ys, high, side="left")
    counts = np.maximum(last - first, 0)
    edge_of_crossing = np.repeat(np.arange(len(x1)), counts)
    return first, counts, edge_of_crossing


def polygon_work(xs: NDArray[np.float64], ys: NDArray[np.float64], polygon: Polygon) -> int:
    """Work ``polygon_mask`` does: cells in the bounding box plus row crossings of the edges."""
    min_x, max_x, min_y, max_y = _bounds(polygon)
    c0, c1 = _index_range(xs, min_x, max_x)
    r0, r1 = _index_range(ys, min_y, max_y)
    x1, y1, _, y2 = _crossing_edges(polygon)
    _, counts, _ = _row_spans(ys, x1, y1, y2)
    return (c1 - c0) * (r1 - r0) + int(counts.sum())


def polygon_mask(
    xs: NDArray[np.float64], ys: NDArray[np.float64], polygon: Polygon
) -> NDArray[np.bool_]:
    """Mask of grid cell centres inside ``polygon``, shape (len(ys), len(xs)).

    ``xs`` (columns) and ``ys`` (rows) must be ascending. Uses the even-odd rule. A centre is inside
    when an odd number of edge crossings of its row lie at or left of it, so a centre exactly on a
    vertical edge counts as inside on the left side of the polygon only.

    Scanline method: for each row the x positions where edges cross the row line are sorted and
    the cells between pairs of crossings are filled, which costs about (cells + crossings) instead
    of (cells x edges).
    """
    mask = np.zeros((ys.size, xs.size), dtype=bool)
    min_x, max_x, min_y, max_y = _bounds(polygon)
    c0, c1 = _index_range(xs, min_x, max_x)
    r0, r1 = _index_range(ys, min_y, max_y)
    if c1 <= c0 or r1 <= r0:
        return mask

    x1, y1, x2, y2 = _crossing_edges(polygon)
    first, counts, edge = _row_spans(ys, x1, y1, y2)
    total = int(counts.sum())
    if total == 0:
        return mask

    # Row and x position of every crossing of an edge with a row line.
    within = np.arange(total) - np.repeat(np.cumsum(counts) - counts, counts)
    rows = first[edge] + within
    py = ys[rows]
    ax, ay, bx, by = x1[edge], y1[edge], x2[edge], y2[edge]
    x_at_row = (bx - ax) * (py - ay) / (by - ay) + ax

    # Sort by row, then x, and pair crossings 1-2, 3-4, ... within each row.
    order = np.lexsort((x_at_row, rows))
    rows, x_at_row = rows[order], x_at_row[order]
    same_row_next = np.zeros(total, dtype=bool)
    same_row_next[:-1] = rows[1:] == rows[:-1]
    row_start = np.flatnonzero(np.r_[True, rows[1:] != rows[:-1]])
    row_length = np.diff(np.r_[row_start, total])
    position = np.arange(total) - np.repeat(row_start, row_length)
    opening = np.flatnonzero((position % 2 == 0) & same_row_next)

    first_col = np.searchsorted(xs, x_at_row[opening], side="left") - c0
    end_col = np.searchsorted(xs, x_at_row[opening + 1], side="left") - c0
    row_index = rows[opening] - r0

    width = c1 - c0
    flat_open = row_index * (width + 1) + first_col
    flat_close = row_index * (width + 1) + end_col
    size = (r1 - r0) * (width + 1)
    delta = np.bincount(flat_open, minlength=size) - np.bincount(flat_close, minlength=size)
    filled = np.cumsum(delta.reshape(r1 - r0, width + 1), axis=1)[:, :width] > 0
    mask[r0:r1, c0:c1] = filled
    return mask
