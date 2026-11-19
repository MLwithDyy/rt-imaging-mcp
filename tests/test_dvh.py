"""Dose-volume metric definitions and slice mapping (pure functions)."""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from rt_imaging_mcp.dvh import (
    dose_at_volume,
    dvh_metrics,
    format_number,
    slice_contributions,
    volume_at_dose,
)

# ------------------------------------------------------- slice contributions (overlap weights)


def approx_entries(entries: list[list[tuple[int, float]]]) -> list[list[tuple[int, Any]]]:
    return [[(index, pytest.approx(weight)) for index, weight in row] for row in entries]


def test_equal_spacing_aligned_slices_have_full_weights() -> None:
    result = slice_contributions([0, 2, 4, 6], 2.0, [0, 2, 4, 6], 2.0)
    assert result == approx_entries([[(0, 1.0)], [(1, 1.0)], [(2, 1.0)], [(3, 1.0)]])


def test_planes_between_slabs_are_shared_and_planes_on_the_outer_boundary_count_half() -> None:
    """Contours 3 mm apart (slabs from -1.5 to 7.5) and dose planes every 1.5 mm."""
    planes = [-1.5, 0.0, 1.5, 3.0, 4.5, 6.0, 7.5]
    result = slice_contributions(planes, 1.5, [0, 3, 6], 3.0)
    assert result == approx_entries(
        [
            [(0, 0.5)],
            [(0, 1.0)],
            [(0, 0.5), (1, 0.5)],
            [(1, 1.0)],
            [(1, 0.5), (2, 0.5)],
            [(2, 1.0)],
            [(2, 0.5)],
        ]
    )


def test_misaligned_slices_share_by_overlap() -> None:
    result = slice_contributions([0, 2, 4, 6, 8, 10, 12], 2.0, [0, 3, 6, 9], 3.0)
    assert result == approx_entries(
        [
            [(0, 1.0)],
            [(0, 0.25), (1, 0.75)],
            [(1, 0.75), (2, 0.25)],
            [(2, 1.0)],
            [(2, 0.25), (3, 0.75)],
            [(3, 0.75)],
            [],
        ]
    )


def test_slices_beyond_the_ends_are_outside() -> None:
    assert slice_contributions([-4.0, 12.0], 2.0, [0, 3, 6, 9], 3.0) == [[], []]


def test_gap_larger_than_one_slab_is_not_bridged() -> None:
    result = slice_contributions([0, 2, 4, 6, 8, 10, 12], 2.0, [0, 2, 4, 12], 2.0)
    assert result == approx_entries([[(0, 1.0)], [(1, 1.0)], [(2, 1.0)], [], [], [], [(3, 1.0)]])


def test_overlapping_slabs_never_add_up_to_more_than_one() -> None:
    result = slice_contributions([1.0], 1.0, [0.0, 1.0, 2.0], 3.0)
    assert sum(weight for _, weight in result[0]) == pytest.approx(1.0)


@pytest.mark.parametrize("dose_step", [1.0, 1.5, 2.0, 2.5, 3.0])
@pytest.mark.parametrize("offset", [0.0, 0.3, 0.75, 1.1])
def test_every_contour_slab_receives_exactly_its_own_thickness(
    dose_step: float, offset: float
) -> None:
    """However the dose planes fall, the structure volume equals the sum of its slabs."""
    contour = [3.0 * index for index in range(10)]
    planes = [-6.0 + offset + dose_step * k for k in range(int(45 / dose_step))]
    received = [0.0] * len(contour)
    for entries in slice_contributions(planes, dose_step, contour, 3.0):
        for index, weight in entries:
            received[index] += weight * dose_step
    assert received == pytest.approx([3.0] * len(contour))


def test_contributions_do_not_depend_on_dose_slice_order() -> None:
    ascending = slice_contributions([0, 2, 4, 6, 8, 10], 2.0, [0, 3, 6, 9], 3.0)
    descending = slice_contributions([10, 8, 6, 4, 2, 0], 2.0, [0, 3, 6, 9], 3.0)
    assert descending == ascending[::-1]


# ---------------------------------------------------------------- D(p) and V(t)


def test_dose_at_volume_basic() -> None:
    doses = np.arange(1, 101, dtype=float)
    assert dose_at_volume(doses, 100.0) == 1.0  # minimum dose
    assert dose_at_volume(doses, 95.0) == 6.0
    assert dose_at_volume(doses, 50.0) == 51.0
    assert dose_at_volume(doses, 1.0) == 100.0  # near maximum


@pytest.mark.parametrize("percent", range(1, 101))
def test_dose_at_volume_is_exact_for_every_integer_percent(percent: int) -> None:
    doses = np.arange(1, 101, dtype=float)
    assert dose_at_volume(doses, float(percent)) == 101 - percent


@pytest.mark.parametrize("step", range(1, 1001))
def test_dose_at_volume_is_robust_to_float_rounding(step: int) -> None:
    doses = np.arange(1, 1001, dtype=float)
    assert dose_at_volume(doses, step / 10.0) == 1001 - step


def test_dose_at_volume_single_voxel() -> None:
    assert dose_at_volume(np.array([7.0]), 50.0) == 7.0
    assert dose_at_volume(np.array([7.0]), 100.0) == 7.0


def test_dose_at_volume_means_at_least_that_volume_receives_the_dose() -> None:
    rng = np.random.default_rng(7)
    doses = np.sort(rng.uniform(0, 60, size=997))
    for percent in (98.0, 95.0, 50.0, 5.0, 2.0):
        d = dose_at_volume(doses, percent)
        covered = np.count_nonzero(doses >= d) / len(doses) * 100
        assert covered >= percent - 1e-9
        higher = doses[doses > d]
        if len(higher):  # the next higher dose must already fall short of the requested volume
            assert np.count_nonzero(doses >= higher.min()) / len(doses) * 100 < percent


def test_volume_at_dose_counts_voxels_at_or_above_threshold() -> None:
    doses = np.array([1.0, 2.0, 3.0, 3.0, 4.0])
    assert volume_at_dose(doses, 3.0) == 3
    assert volume_at_dose(doses, 3.0001) == 1
    assert volume_at_dose(doses, 0.0) == 5
    assert volume_at_dose(doses, 5.0) == 0


def test_volume_at_dose_absorbs_floating_point_error() -> None:
    doses = np.array([19.999999999999996, 20.0, 20.000000000000004])
    assert volume_at_dose(doses, 20.0) == 3


# ---------------------------------------------------------------- full metrics


def gradient_doses() -> np.ndarray:
    return np.repeat([10.0, 12.0, 14.0, 16.0, 18.0], 25)  # 125 voxels


def test_metrics_for_a_known_distribution() -> None:
    result = dvh_metrics(gradient_doses(), 8.0, [95.0, 50.0, 2.0], [16.0, 20.0])
    assert result["dose_gy"] == {"min": 10.0, "max": 18.0, "mean": 14.0}
    assert result["d_metrics_gy"] == {"D95": 10.0, "D50": 14.0, "D2": 18.0}
    assert result["v_metrics"]["V16Gy"] == {"percent": 40.0, "volume_cm3": 0.4}
    assert result["v_metrics"]["V20Gy"] == {"percent": 0.0, "volume_cm3": 0.0}


def test_metrics_keys_are_compact() -> None:
    result = dvh_metrics(gradient_doses(), 8.0, [95.0, 2.5, 100.0], [20.0, 0.5])
    assert list(result["d_metrics_gy"]) == ["D95", "D2.5", "D100"]
    assert list(result["v_metrics"]) == ["V20Gy", "V0.5Gy"]


def test_metrics_without_requested_values() -> None:
    result = dvh_metrics(gradient_doses(), 8.0, [], [])
    assert result["d_metrics_gy"] == {}
    assert result["v_metrics"] == {}
    assert result["dose_gy"]["mean"] == 14.0


def test_metrics_do_not_depend_on_voxel_order() -> None:
    doses = gradient_doses()
    shuffled = np.random.default_rng(1).permutation(doses)
    assert dvh_metrics(doses, 8.0, [95.0, 50.0], [15.0]) == dvh_metrics(
        shuffled, 8.0, [95.0, 50.0], [15.0]
    )


def test_uniform_dose_has_equal_metrics() -> None:
    result = dvh_metrics(np.full(40, 20.0), 8.0, [95.0, 50.0, 2.0], [20.0])
    assert set(result["d_metrics_gy"].values()) == {20.0}
    assert result["v_metrics"]["V20Gy"]["percent"] == 100.0


@pytest.mark.parametrize(
    ("value", "text"), [(95.0, "95"), (2.5, "2.5"), (20.0, "20"), (0.5, "0.5")]
)
def test_format_number(value: float, text: str) -> None:
    assert format_number(value) == text


# ------------------------------------------------------------------ weighted metrics


def test_equal_weights_give_exactly_the_unweighted_values() -> None:
    doses = np.arange(1, 1001, dtype=float)
    ones = np.ones_like(doses)
    for step in range(1, 1001):
        percent = step / 10.0
        assert dose_at_volume(doses, percent, ones) == dose_at_volume(doses, percent)


def test_weighted_percentiles_and_volume() -> None:
    doses = np.array([10.0, 20.0, 30.0])
    weights = np.array([1.0, 2.0, 1.0])  # total weight 4
    assert dose_at_volume(doses, 25.0, weights) == 30.0
    assert dose_at_volume(doses, 50.0, weights) == 20.0
    assert dose_at_volume(doses, 75.0, weights) == 20.0
    assert dose_at_volume(doses, 100.0, weights) == 10.0
    assert volume_at_dose(doses, 20.0, weights) == 3.0
    assert volume_at_dose(doses, 25.0, weights) == 1.0


def test_metrics_with_weights() -> None:
    doses = np.array([30.0, 10.0, 20.0])  # unsorted on purpose
    weights = np.array([1.0, 1.0, 2.0])
    result = dvh_metrics(doses, 1000.0, [50.0], [20.0], weights)
    assert result["dose_gy"] == {"min": 10.0, "max": 30.0, "mean": 20.0}
    assert result["d_metrics_gy"] == {"D50": 20.0}
    assert result["v_metrics"]["V20Gy"] == {"percent": 75.0, "volume_cm3": 3.0}


def test_partially_covered_end_voxels_count_only_with_their_weight() -> None:
    doses = np.array([1.0, 2.0, 3.0, 4.0])
    weights = np.array([0.5, 1.0, 1.0, 0.5])
    result = dvh_metrics(doses, 1000.0, [], [2.0], weights)
    assert result["dose_gy"]["mean"] == pytest.approx(2.5)
    assert result["v_metrics"]["V2Gy"]["volume_cm3"] == pytest.approx(2.5)
