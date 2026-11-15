"""DICOM tag allowlist (rule R1).

Only attributes listed here can ever be returned. There is no denylist logic:
a tag that is not on the allowlist is rejected, including private tags and
attributes added to DICOM in the future.

``ALWAYS_BLOCKED_KEYWORDS`` is documentation and a test invariant: it must never
overlap with the allowed sets. Nothing in this module reads from it at runtime
to decide what to return.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from rt_imaging_mcp.security.errors import TagNotAllowedError

# Technical attributes. Safe to return by default.
DEFAULT_KEYWORDS: frozenset[str] = frozenset(
    {
        "Modality",
        "Rows",
        "Columns",
        "NumberOfFrames",
        "SamplesPerPixel",
        "BitsAllocated",
        "BitsStored",
        "HighBit",
        "PixelRepresentation",
        "PhotometricInterpretation",
        "PixelSpacing",
        "SliceThickness",
        "SpacingBetweenSlices",
        "ImageOrientationPatient",
        "ImagePositionPatient",
        "SOPClassUID",
        "TransferSyntaxUID",
        "RescaleSlope",
        "RescaleIntercept",
    }
)

# Can carry indirect identifiers or free text. Off unless the user enables them explicitly.
OPT_IN_KEYWORDS: frozenset[str] = frozenset(
    {
        "StudyDate",
        "StudyTime",
        "SeriesDate",
        "SeriesTime",
        "AcquisitionDate",
        "AcquisitionTime",
        "ContentDate",
        "ContentTime",
        "StudyDescription",
        "SeriesDescription",
        "ProtocolName",
        "BodyPartExamined",
        "Manufacturer",
        "ManufacturerModelName",
        "SoftwareVersions",
        "StudyInstanceUID",
        "SeriesInstanceUID",
        "SOPInstanceUID",
        "FrameOfReferenceUID",
    }
)

# Direct identifiers and similar. Can never be enabled. Kept for tests and documentation.
ALWAYS_BLOCKED_KEYWORDS: frozenset[str] = frozenset(
    {
        "PatientName",
        "PatientID",
        "PatientBirthDate",
        "PatientBirthTime",
        "PatientSex",
        "PatientAge",
        "PatientSize",
        "PatientWeight",
        "PatientAddress",
        "PatientTelephoneNumbers",
        "PatientComments",
        "OtherPatientIDs",
        "OtherPatientNames",
        "PatientMotherBirthName",
        "MedicalRecordLocator",
        "AdditionalPatientHistory",
        "EthnicGroup",
        "Occupation",
        "InstitutionName",
        "InstitutionAddress",
        "InstitutionalDepartmentName",
        "ReferringPhysicianName",
        "PerformingPhysicianName",
        "PhysiciansOfRecord",
        "NameOfPhysiciansReadingStudy",
        "RequestingPhysician",
        "OperatorsName",
        "AccessionNumber",
        "StudyID",
        "DeviceSerialNumber",
        "StationName",
        "ImageComments",
    }
)

ALL_ALLOWABLE_KEYWORDS: frozenset[str] = DEFAULT_KEYWORDS | OPT_IN_KEYWORDS


def resolve_keywords(
    requested: Iterable[str] | None,
    enabled_opt_in: frozenset[str] = frozenset(),
) -> tuple[str, ...]:
    """Return the keywords a tool may read.

    ``requested=None`` means "everything currently allowed". Any requested keyword
    that is not currently allowed raises ``TagNotAllowedError``.
    """
    allowed = DEFAULT_KEYWORDS | (enabled_opt_in & OPT_IN_KEYWORDS)
    if requested is None:
        return tuple(sorted(allowed))

    resolved: list[str] = []
    for keyword in requested:
        if not isinstance(keyword, str) or keyword not in allowed:
            raise TagNotAllowedError()
        if keyword not in resolved:
            resolved.append(keyword)
    return tuple(resolved)


def to_jsonable(value: Any) -> Any:
    """Convert a pydicom value to plain JSON types. Unknown types become ``None``."""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return float(value)
    if isinstance(value, str):
        return str(value)
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        return [to_jsonable(item) for item in value]
    return None


def _lookup(dataset: Any, keyword: str) -> Any:
    value = dataset.get(keyword)
    if value is None:
        file_meta = getattr(dataset, "file_meta", None)
        if file_meta is not None:
            value = file_meta.get(keyword)
    return value


def filter_dataset(dataset: Any, keywords: Iterable[str]) -> dict[str, Any]:
    """Read ``keywords`` from a pydicom dataset and return JSON-safe values.

    Defense in depth: even when called with keywords that were not vetted by
    ``resolve_keywords``, anything outside the allowable universe is rejected.
    Attributes are fetched by keyword only, so private tags are never touched.
    """
    result: dict[str, Any] = {}
    for keyword in keywords:
        if keyword not in ALL_ALLOWABLE_KEYWORDS:
            raise TagNotAllowedError()
        value = _lookup(dataset, keyword)
        if value is None:
            continue
        converted = to_jsonable(value)
        if converted is None:
            continue
        result[keyword] = converted
    return result
