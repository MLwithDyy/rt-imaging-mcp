"""Planar geometry helpers used for approximate contour volumes."""

from __future__ import annotations

import numpy as np
import pytest

from rt_imaging_mcp.geometry import net_slice_area, point_in_polygon, polygon_area


def poly(*points: tuple[float, float]) -> np.ndarray:
    return np.array(points, dtype=float)


def square(x0: float, y0: float, size: float) -> np.ndarray:
    return poly((x0, y0), (x0 + size, y0), (x0 + size, y0 + size), (x0, y0 + size))


def test_square_area() -> None:
    assert polygon_area(square(0, 0, 10)) == pytest.approx(100.0)


def test_triangle_area() -> None:
    assert polygon_area(poly((0, 0), (4, 0), (0, 3))) == pytest.approx(6.0)


def test_area_is_independent_of_orientation_and_start_vertex() -> None:
    clockwise = square(0, 0, 5)[::-1]
    rolled = np.roll(square(0, 0, 5), 2, axis=0)
    assert polygon_area(clockwise) == pytest.approx(25.0)
    assert polygon_area(rolled) == pytest.approx(25.0)


def test_concave_polygon_area() -> None:
    # L shape made from a 10x10 square minus a 5x5 corner
    shape = poly((0, 0), (10, 0), (10, 5), (5, 5), (5, 10), (0, 10))
    assert polygon_area(shape) == pytest.approx(75.0)


@pytest.mark.parametrize(
    ("point", "expected"),
    [((5, 5), True), ((0.1, 0.1), True), ((11, 5), False), ((-1, 5), False), ((5, 11), False)],
)
def test_point_in_square(point: tuple[float, float], expected: bool) -> None:
    assert point_in_polygon(point, square(0, 0, 10)) is expected


def test_point_in_concave_polygon() -> None:
    shape = poly((0, 0), (10, 0), (10, 5), (5, 5), (5, 10), (0, 10))
    assert point_in_polygon((2, 8), shape) is True
    assert point_in_polygon((8, 8), shape) is False  # inside the notch


def test_single_contour_area() -> None:
    assert net_slice_area([square(0, 0, 10)]) == pytest.approx(100.0)


def test_two_separate_contours_add() -> None:
    assert net_slice_area([square(0, 0, 10), square(20, 0, 5)]) == pytest.approx(125.0)


def test_nested_contour_is_a_hole() -> None:
    assert net_slice_area([square(0, 0, 20), square(5, 5, 10)]) == pytest.approx(300.0)


def test_hole_orientation_does_not_matter() -> None:
    assert net_slice_area([square(0, 0, 20), square(5, 5, 10)[::-1]]) == pytest.approx(300.0)


def test_island_inside_hole_counts_as_material_again() -> None:
    contours = [square(0, 0, 30), square(5, 5, 20), square(10, 10, 10)]
    assert net_slice_area(contours) == pytest.approx(900.0 - 400.0 + 100.0)


def test_empty_slice_has_zero_area() -> None:
    assert net_slice_area([]) == 0.0
