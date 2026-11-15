"""Rule R1, R2 (no pixel data), R6 (no data in errors)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydicom.datadict import tag_for_keyword

from rt_imaging_mcp.config import Config
from rt_imaging_mcp.security.allowlist import (
    ALL_ALLOWABLE_KEYWORDS,
    ALWAYS_BLOCKED_KEYWORDS,
    DEFAULT_KEYWORDS,
    OPT_IN_KEYWORDS,
    filter_dataset,
    resolve_keywords,
    to_jsonable,
)
from rt_imaging_mcp.security.errors import ConfigError, TagNotAllowedError
from tests.synthetic import FAKE_DESCRIPTION, IDENTIFYING_VALUES, build_ct_dataset


def test_sets_are_disjoint() -> None:
    assert not DEFAULT_KEYWORDS & OPT_IN_KEYWORDS
    assert not ALWAYS_BLOCKED_KEYWORDS & DEFAULT_KEYWORDS
    assert not ALWAYS_BLOCKED_KEYWORDS & OPT_IN_KEYWORDS


@pytest.mark.parametrize(
    "keywords",
    [DEFAULT_KEYWORDS, OPT_IN_KEYWORDS, ALWAYS_BLOCKED_KEYWORDS],
    ids=["default", "opt_in", "blocked"],
)
def test_every_keyword_is_a_real_dicom_keyword(keywords: frozenset[str]) -> None:
    unknown = [kw for kw in keywords if tag_for_keyword(kw) is None]
    assert unknown == []


def test_pixel_data_is_not_allowable() -> None:
    assert "PixelData" not in ALL_ALLOWABLE_KEYWORDS


def test_default_resolution_returns_only_default_keywords() -> None:
    assert set(resolve_keywords(None)) == set(DEFAULT_KEYWORDS)


@pytest.mark.parametrize("keyword", sorted(ALWAYS_BLOCKED_KEYWORDS))
def test_blocked_keywords_are_rejected(keyword: str) -> None:
    with pytest.raises(TagNotAllowedError):
        resolve_keywords([keyword])


@pytest.mark.parametrize("keyword", sorted(ALWAYS_BLOCKED_KEYWORDS))
def test_blocked_keywords_cannot_be_enabled_through_opt_in(keyword: str) -> None:
    allowed = resolve_keywords(None, enabled_opt_in=frozenset({keyword}))
    assert keyword not in allowed
    with pytest.raises(TagNotAllowedError):
        resolve_keywords([keyword], enabled_opt_in=frozenset({keyword}))


def test_opt_in_keyword_needs_explicit_enable() -> None:
    with pytest.raises(TagNotAllowedError):
        resolve_keywords(["StudyDescription"])
    assert resolve_keywords(["StudyDescription"], frozenset({"StudyDescription"})) == (
        "StudyDescription",
    )


@pytest.mark.parametrize("bad", ["PixelData", "NotARealTag", "", "00100010", "(0010,0010)"])
def test_unknown_or_private_style_requests_are_rejected(bad: str) -> None:
    with pytest.raises(TagNotAllowedError):
        resolve_keywords([bad])


def test_non_string_keyword_rejected() -> None:
    with pytest.raises(TagNotAllowedError):
        resolve_keywords([0x00100010])  # type: ignore[list-item]


def test_duplicate_requests_are_collapsed() -> None:
    assert resolve_keywords(["Rows", "Rows", "Columns"]) == ("Rows", "Columns")


def test_filter_never_returns_identifiers_with_defaults() -> None:
    ds = build_ct_dataset()
    output = filter_dataset(ds, resolve_keywords(None))
    serialized = json.dumps(output)
    for value in IDENTIFYING_VALUES:
        assert value not in serialized
    assert output["Modality"] == "CT"
    assert output["Rows"] == 4
    assert output["PixelSpacing"] == [0.5, 0.5]


def test_filter_never_returns_identifiers_with_every_opt_in_enabled() -> None:
    ds = build_ct_dataset()
    keywords = resolve_keywords(None, enabled_opt_in=OPT_IN_KEYWORDS)
    output = filter_dataset(ds, keywords)
    serialized = json.dumps(output)
    for value in IDENTIFYING_VALUES:
        assert value not in serialized
    # Opt-in text is returned only because it was explicitly enabled.
    assert output["StudyDescription"] == FAKE_DESCRIPTION


def test_opt_in_text_absent_by_default() -> None:
    output = filter_dataset(build_ct_dataset(), resolve_keywords(None))
    assert "StudyDescription" not in output
    assert "StudyDate" not in output


def test_private_tags_never_returned() -> None:
    ds = build_ct_dataset()
    keywords = resolve_keywords(None, enabled_opt_in=OPT_IN_KEYWORDS)
    serialized = json.dumps(filter_dataset(ds, keywords))
    assert "SYNTH PRIVATE" not in serialized


def test_no_pixel_data_in_output() -> None:
    ds = build_ct_dataset()
    keywords = resolve_keywords(None, enabled_opt_in=OPT_IN_KEYWORDS)
    output = filter_dataset(ds, keywords)
    assert "PixelData" not in output
    assert len(json.dumps(output)) < 5_000


def test_filter_rejects_unvetted_keywords_as_defense_in_depth() -> None:
    ds = build_ct_dataset()
    with pytest.raises(TagNotAllowedError):
        filter_dataset(ds, ["PatientName"])
    with pytest.raises(TagNotAllowedError):
        filter_dataset(ds, ["PixelData"])


def test_transfer_syntax_comes_from_file_meta() -> None:
    output = filter_dataset(build_ct_dataset(), ["TransferSyntaxUID"])
    assert output["TransferSyntaxUID"] == "1.2.840.10008.1.2.1"


def test_missing_attributes_are_skipped() -> None:
    ds = build_ct_dataset()
    del ds.SliceThickness
    assert "SliceThickness" not in filter_dataset(ds, ["SliceThickness", "Rows"])


def test_output_is_json_serializable() -> None:
    ds = build_ct_dataset()
    keywords = resolve_keywords(None, enabled_opt_in=OPT_IN_KEYWORDS)
    json.dumps(filter_dataset(ds, keywords))


def test_to_jsonable_handles_types() -> None:
    assert to_jsonable(3) == 3
    assert to_jsonable(2.5) == 2.5
    assert to_jsonable("x") == "x"
    assert to_jsonable([1, 2.0, "a"]) == [1, 2.0, "a"]
    assert to_jsonable(b"\x00\x01") is None
    assert to_jsonable(object()) is None


def test_error_messages_do_not_echo_input() -> None:
    with pytest.raises(TagNotAllowedError) as info:
        resolve_keywords(["PatientName"])
    assert "PatientName" not in str(info.value)


def test_config_rejects_blocked_tags_as_opt_in(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        Config.from_root(tmp_path, enabled_opt_in_tags=frozenset({"PatientName"}))
