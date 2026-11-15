"""Rule R10: structure names are standardised or redacted."""

from __future__ import annotations

import pytest

from rt_imaging_mcp.security.roi_names import (
    MAX_NAME_LENGTH,
    STANDARD_ROI_NAMES,
    standardize_roi_name,
)


@pytest.mark.parametrize("name", sorted(STANDARD_ROI_NAMES))
def test_every_standard_name_maps_to_itself(name: str) -> None:
    assert standardize_roi_name(name) == name


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("bladder", "Bladder"),
        ("BLADDER", "Bladder"),
        ("  Rectum  ", "Rectum"),
        ("Bowel Large", "Bowel_Large"),
        ("femur-head-l", "Femur_Head_L"),
        ("spinalcord", "SpinalCord"),
        ("body", "BODY"),
    ],
)
def test_case_and_separator_variants_are_canonicalised(given: str, expected: str) -> None:
    assert standardize_roi_name(given) == expected


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("PTV", "PTV"),
        ("ptv", "PTV"),
        ("GTV", "GTV"),
        ("gtvp", "GTVp"),
        ("GTVn2", "GTVn2"),
        ("CTV_High", "CTV_High"),
        ("ptv_low", "PTV_Low"),
        ("PTV_5000", "PTV_5000"),
        ("PTV_50Gy", "PTV_50Gy"),
        ("ptv_5000cgy", "PTV_5000cGy"),
        ("ITV_High_5040", "ITV_High_5040"),
    ],
)
def test_target_volume_patterns(given: str, expected: str) -> None:
    assert standardize_roi_name(given) == expected


@pytest.mark.parametrize(
    "name",
    [
        "PTV_Budi",
        "PTV_High_Budi",
        "Budi",
        "Kasus 12 Bu Siti",
        "SYNTHROI_Budi",
        "Rectum_Budi",
        "Bladder (Siti)",
        "PTV_RSUD",
        "PTV 50 Gy",  # "50" and "Gy" are separate tokens
        "PTV_",
        "GTVx",
        "PTV123456",
        "Femur_Head_L_Budi",
        "",
        "   ",
        "_",
        "-",
    ],
)
def test_names_with_other_text_are_redacted(name: str) -> None:
    assert standardize_roi_name(name) is None


def test_overlong_name_is_redacted() -> None:
    assert standardize_roi_name("PTV_" + "High_" * 30) is None
    assert standardize_roi_name("A" * (MAX_NAME_LENGTH + 1)) is None


@pytest.mark.parametrize("value", [None, 5, 3.2, b"PTV", ["PTV"]])
def test_non_string_names_are_redacted(value: object) -> None:
    assert standardize_roi_name(value) is None


def test_returned_names_never_echo_arbitrary_input() -> None:
    """Whatever comes back is composed only of known tokens, never of the raw input text."""
    attempts = [
        "PTV_Budi_Santoso",
        "BLADDER_budi",
        "Ptv_high",
        "pTv5000",
        "gtv_Siti",
        "PTV\u202e_Budi",
        "PTV\nBudi",
    ]
    for attempt in attempts:
        result = standardize_roi_name(attempt)
        assert result is None or "budi" not in result.casefold()
        assert result is None or "siti" not in result.casefold()


def test_operator_enabled_names_are_returned_in_the_operators_spelling() -> None:
    extra = frozenset({"Rectum_Spare", "Kandung Kemih"})
    assert standardize_roi_name("rectum_spare", extra) == "Rectum_Spare"
    assert standardize_roi_name("KANDUNG KEMIH", extra) == "Kandung_Kemih"
    assert standardize_roi_name("Other_Name", extra) is None


def test_extra_names_do_not_change_standard_behaviour() -> None:
    assert standardize_roi_name("bladder", frozenset({"Foo"})) == "Bladder"
