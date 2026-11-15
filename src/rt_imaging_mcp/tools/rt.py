"""Radiotherapy tools: summary of an RT structure set (RTSTRUCT).

Only structural information is returned. Structure names are standardised or
redacted (R10). Free-text fields (structure set label, observation labels,
ROI descriptions) and absolute patient coordinates are never returned.
"""

from __future__ import annotations

from itertools import islice
from typing import Any

import numpy as np

from rt_imaging_mcp.config import Config
from rt_imaging_mcp.geometry import Polygon, net_slice_area
from rt_imaging_mcp.security.errors import NotRtStructError, RtImagingMcpError
from rt_imaging_mcp.security.roi_names import standardize_roi_name
from rt_imaging_mcp.tools.dicom import read_header
from rt_imaging_mcp.tools.rt_common import code as _code
from rt_imaging_mcp.tools.rt_common import prepare_rt_file

MAX_ROIS = 1000
MAX_CONTOURS_PER_ROI = 20_000

# DICOM code strings (enumerated values). Anything else is reported as null.
INTERPRETED_TYPES = frozenset(
    {
        "EXTERNAL",
        "PTV",
        "CTV",
        "GTV",
        "TREATED_VOLUME",
        "IRRAD_VOLUME",
        "BOLUS",
        "AVOIDANCE",
        "ORGAN",
        "MARKER",
        "REGISTRATION",
        "ISOCENTER",
        "CONTRAST_AGENT",
        "CAVITY",
        "BRACHY_CHANNEL",
        "BRACHY_ACCESSORY",
        "BRACHY_SRC_APP",
        "BRACHY_CHNL_SHLD",
        "SUPPORT",
        "FIXATION",
        "DOSE_REGION",
        "CONTROL",
    }
)
GENERATION_ALGORITHMS = frozenset({"AUTOMATIC", "SEMIAUTOMATIC", "MANUAL"})
GEOMETRIC_TYPES = frozenset({"POINT", "OPEN_PLANAR", "OPEN_NONPLANAR", "CLOSED_PLANAR"})


def _roi_geometry(contour_sequence: Any) -> dict[str, Any]:
    """Contour statistics for one ROI. Coordinates are reduced to sizes and counts."""
    contour_count = 0
    invalid = 0
    geometric_types: set[str] = set()
    slices: dict[float, list[Polygon]] = {}
    minimum: np.ndarray[Any, Any] | None = None
    maximum: np.ndarray[Any, Any] | None = None
    total = len(contour_sequence) if contour_sequence is not None else 0

    for item in islice(contour_sequence or [], MAX_CONTOURS_PER_ROI):
        try:
            points = np.asarray(item.get("ContourData"), dtype=float).reshape(-1, 3)
        except (TypeError, ValueError):
            invalid += 1
            continue
        if points.size == 0 or not np.all(np.isfinite(points)):
            invalid += 1
            continue

        contour_count += 1
        geometric = _code(item.get("ContourGeometricType"), GEOMETRIC_TYPES)
        if geometric is not None:
            geometric_types.add(geometric)
        low, high = points.min(axis=0), points.max(axis=0)
        minimum = low if minimum is None else np.minimum(minimum, low)
        maximum = high if maximum is None else np.maximum(maximum, high)
        if geometric == "CLOSED_PLANAR" and len(points) >= 3:
            z = round(float(points[:, 2].mean()), 2)
            slices.setdefault(z, []).append(points[:, :2])

    capped = total > MAX_CONTOURS_PER_ROI
    volume: float | None = None
    if len(slices) >= 2 and not capped:
        z_values = sorted(slices)
        spacing = float(np.median(np.diff(z_values)))
        if spacing > 0:
            area = sum(net_slice_area(polygons) for polygons in slices.values())
            volume = round(area * spacing / 1000.0, 3)

    extent = None
    if minimum is not None and maximum is not None:
        extent = [round(float(size), 2) for size in (maximum - minimum)]

    return {
        "contour_count": contour_count,
        "invalid_contours": invalid,
        "geometric_types": sorted(geometric_types),
        "slice_count": len(slices),
        "extent_mm": extent,
        "approx_volume_cm3": volume,
        "contours_truncated": capped,
    }


def rt_structure_summary(config: Config, path: str) -> dict[str, Any]:
    """Summarise an RTSTRUCT file: one entry per structure, with standardised names only.

    ``approx_volume_cm3`` is a planar-contour approximation (sum of net slice areas times the
    median slice spacing). It is not a clinical volume and is not validated against a treatment
    planning system.
    """
    file = prepare_rt_file(config, path)
    header = read_header(file)
    try:
        if str(header.get("Modality", "")).strip().upper() != "RTSTRUCT":
            raise NotRtStructError()

        observations: dict[int, Any] = {}
        for observation in header.get("RTROIObservationsSequence") or []:
            observations[int(observation.ReferencedROINumber)] = observation.get(
                "RTROIInterpretedType"
            )

        contours: dict[int, Any] = {}
        for roi_contour in header.get("ROIContourSequence") or []:
            contours[int(roi_contour.ReferencedROINumber)] = roi_contour.get("ContourSequence")

        definitions = sorted(
            header.get("StructureSetROISequence") or [], key=lambda item: int(item.ROINumber)
        )
        truncated = len(definitions) > MAX_ROIS

        rois: list[dict[str, Any]] = []
        by_type: dict[str, int] = {}
        for definition in definitions[:MAX_ROIS]:
            number = int(definition.ROINumber)
            name = standardize_roi_name(definition.get("ROIName"), config.extra_roi_names)
            interpreted = _code(observations.get(number), INTERPRETED_TYPES)
            by_type[interpreted or "UNKNOWN"] = by_type.get(interpreted or "UNKNOWN", 0) + 1
            rois.append(
                {
                    "roi_number": number,
                    "name": name,
                    "name_redacted": name is None,
                    "interpreted_type": interpreted,
                    "generation_algorithm": _code(
                        definition.get("ROIGenerationAlgorithm"), GENERATION_ALGORITHMS
                    ),
                    **_roi_geometry(contours.get(number)),
                }
            )
    except RtImagingMcpError:
        raise
    except Exception:
        raise NotRtStructError() from None

    return {
        "roi_count": len(definitions),
        "rois": rois,
        "counts_by_interpreted_type": dict(sorted(by_type.items())),
        "truncated": truncated,
    }
