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


# ---------------------------------------------------------------- rasterisation

from rt_imaging_mcp.geometry import polygon_mask, polygon_work  # noqa: E402


def axis(start: float, stop: float, step: float) -> np.ndarray:
    return np.arange(start, stop, step, dtype=float)


def test_mask_of_square_counts_cell_centres() -> None:
    xs = ys = axis(0, 12, 2)  # centres 0, 2, ..., 10
    mask = polygon_mask(xs, ys, square(-1, -1, 10))  # covers x, y in [-1, 9]
    assert mask.shape == (6, 6)
    assert mask.sum() == 25
    assert mask[:5, :5].all()
    assert not mask[5, :].any()
    assert not mask[:, 5].any()


def test_mask_rows_follow_y_and_columns_follow_x() -> None:
    xs = axis(0, 20, 2)  # 10 columns
    ys = axis(0, 10, 2)  # 5 rows
    rectangle = poly((-1, -1), (5, -1), (5, 3), (-1, 3))  # x in [-1, 5], y in [-1, 3]
    mask = polygon_mask(xs, ys, rectangle)
    assert mask.shape == (5, 10)
    assert np.argwhere(mask).tolist() == [[0, 0], [0, 1], [0, 2], [1, 0], [1, 1], [1, 2]]


def test_l_shape_cell_count_matches_area_exactly() -> None:
    xs = ys = axis(0.5, 10, 1.0)  # unit cells, centres at .5
    shape = poly((0, 0), (10, 0), (10, 5), (5, 5), (5, 10), (0, 10))
    assert polygon_mask(xs, ys, shape).sum() == 75


def test_triangle_cell_count_is_close_to_area() -> None:
    # Centres at 0.02 + 0.05 k never lie exactly on the hypotenuse x + y = 10.
    xs = ys = axis(0.02, 10, 0.05)
    triangle = poly((0, 0), (10, 0), (0, 10))
    cells = polygon_mask(xs, ys, triangle).sum()
    assert cells * 0.05 * 0.05 == pytest.approx(50.0, rel=0.01)


def test_mask_with_hole_by_xor() -> None:
    xs = ys = axis(0, 20, 2)
    outer = polygon_mask(xs, ys, square(-1, -1, 12))  # centres 0..10 -> 6 x 6
    hole = polygon_mask(xs, ys, square(3, 3, 4))  # centres 4, 6 -> 2 x 2
    assert (outer ^ hole).sum() == 36 - 4


def test_mask_orientation_of_polygon_does_not_matter() -> None:
    xs = ys = axis(0, 12, 2)
    forward = polygon_mask(xs, ys, square(-1, -1, 10))
    backward = polygon_mask(xs, ys, square(-1, -1, 10)[::-1])
    assert (forward == backward).all()


def test_polygon_outside_grid_gives_empty_mask() -> None:
    xs = ys = axis(0, 12, 2)
    assert not polygon_mask(xs, ys, square(100, 100, 10)).any()
    assert not polygon_mask(xs, ys, square(-50, -50, 10)).any()


def test_polygon_partly_outside_grid_is_clipped() -> None:
    xs = ys = axis(0, 12, 2)
    assert polygon_mask(xs, ys, square(7, -1, 10)).sum() == 2 * 5  # x centres 8 and 10 only


def test_polygon_between_grid_centres_gives_empty_mask() -> None:
    xs = ys = axis(0, 12, 2)
    assert not polygon_mask(xs, ys, square(0.5, 0.5, 1)).any()


def test_polygon_work_is_bounding_box_cells_times_crossing_edges() -> None:
    xs = ys = axis(0, 12, 2)
    # 5 x 5 cells in the bounding box, 2 non-horizontal edges
    assert polygon_work(xs, ys, square(-1, -1, 10)) == 5 * 5 * 2
