"""RT dose-volume tool: dose statistics and D/V metrics for one structure.

Combines an RTSTRUCT and an RTDOSE file. Only numbers are returned. The structure
name is standardised or redacted (R10); UIDs, positions and free text are never
returned (R11).

Method (approximate, not validated against a treatment planning system):

* A dose voxel belongs to the structure when its centre lies inside the structure's
  contours on the contour slice that covers it. Nested contours on one slice are holes
  (even-odd rule). There is no partial-volume weighting.
* Each contour slice represents a slab as thick as the median contour slice spacing.
  A dose slice uses the nearest contour slice if it lies inside that slab, otherwise it
  is outside the structure. Contour gaps larger than one slab stay gaps.
* The dose grid must be axis aligned (orientation 1,0,0,0,1,0), in Gy, with at least two
  uniformly spaced slices, and must share its frame of reference with the structure set.
"""

from __future__ import annotations

from itertools import islice
from typing import Any

import numpy as np

from rt_imaging_mcp.config import Config
from rt_imaging_mcp.dvh import dvh_metrics, nearest_slice_indices
from rt_imaging_mcp.geometry import net_slice_area, polygon_mask, polygon_work
from rt_imaging_mcp.security.errors import (
    FrameOfReferenceError,
    InvalidParameterError,
    NoStructureVoxelsError,
    NotRtDoseError,
    NotRtStructError,
    RtImagingMcpError,
    StructureNotFoundError,
    UnsupportedGridError,
    WorkLimitError,
)
from rt_imaging_mcp.security.roi_names import standardize_roi_name
from rt_imaging_mcp.tools.dicom import read_header
from rt_imaging_mcp.tools.rt import MAX_CONTOURS_PER_ROI
from rt_imaging_mcp.tools.rt_common import (
    code,
    contour_polygon,
    number,
    prepare_rt_file,
    read_with_pixels,
)

MAX_PARAMETERS = 20
MAX_RASTER_WORK = 400_000_000
DEFAULT_PERCENTAGES = (95.0, 50.0, 2.0)
DEFAULT_THRESHOLDS_GY = (20.0,)
MAX_THRESHOLD_GY = 10_000.0
_TOLERANCE_MM = 1e-6

METHOD_NOTES = (
    "voxel centres inside contours; nested contours are holes",
    "nearest contour slice within one slab; no partial-volume weighting",
    "approximate; not validated against a treatment planning system",
)


def _parameters(
    values: Any,
    default: tuple[float, ...],
    *,
    lower: float,
    lower_inclusive: bool,
    upper: float,
) -> list[float]:
    if values is None:
        return list(default)
    if not isinstance(values, list | tuple) or len(values) > MAX_PARAMETERS:
        raise InvalidParameterError()
    result: list[float] = []
    for value in values:
        # Parameters come from a client as JSON numbers. Numeric strings are rejected.
        parsed = None if isinstance(value, str | bytes | bool) else number(value)
        if parsed is None or parsed > upper:
            raise InvalidParameterError()
        if parsed < lower or (parsed == lower and not lower_inclusive):
            raise InvalidParameterError()
        if parsed not in result:
            result.append(parsed)
    return result


def _frame_of_reference_of_structure_set(header: Any) -> str:
    sequence = header.get("ReferencedFrameOfReferenceSequence") or []
    if len(sequence) == 0:
        return ""
    return str(sequence[0].get("FrameOfReferenceUID") or "").strip()


def _load_structure(
    config: Config, struct_path: str, roi_number: int
) -> tuple[dict[float, list[Any]], Any, str]:
    """Contours by slice, the ROI definition and the frame of reference UID."""
    file = prepare_rt_file(config, struct_path)
    header = read_header(file)
    try:
        if str(header.get("Modality", "")).strip().upper() != "RTSTRUCT":
            raise NotRtStructError()
        definition = next(
            (
                item
                for item in header.get("StructureSetROISequence") or []
                if int(item.ROINumber) == roi_number
            ),
            None,
        )
        roi_contour = next(
            (
                item
                for item in header.get("ROIContourSequence") or []
                if int(item.ReferencedROINumber) == roi_number
            ),
            None,
        )
        if definition is None or roi_contour is None:
            raise StructureNotFoundError()

        sequence = roi_contour.get("ContourSequence") or []
        if len(sequence) > MAX_CONTOURS_PER_ROI:
            raise WorkLimitError()
        slices: dict[float, list[Any]] = {}
        for item in islice(sequence, MAX_CONTOURS_PER_ROI):
            parsed = contour_polygon(item)
            if parsed is not None:
                z, polygon = parsed
                slices.setdefault(z, []).append(polygon)
        if not slices:
            raise StructureNotFoundError()
        return slices, definition, _frame_of_reference_of_structure_set(header)
    except RtImagingMcpError:
        raise
    except Exception:
        raise NotRtStructError() from None


def rt_dvh_metrics(
    config: Config,
    struct_path: str,
    dose_path: str,
    roi_number: int,
    dose_percentages: list[float] | None = None,
    volume_thresholds_gy: list[float] | None = None,
) -> dict[str, Any]:
    """Dose statistics, D(p) and V(t) for one structure of an RTSTRUCT on an RTDOSE grid.

    ``D95`` is the highest dose that at least 95 % of the structure volume receives or exceeds.
    ``V20Gy`` is the percentage and volume of the structure receiving at least 20 Gy.
    """
    if (
        isinstance(roi_number, bool)
        or not isinstance(roi_number, int)
        or not 0 <= roi_number < 2**31
    ):
        raise InvalidParameterError()
    percentages = _parameters(
        dose_percentages, DEFAULT_PERCENTAGES, lower=0.0, lower_inclusive=False, upper=100.0
    )
    thresholds = _parameters(
        volume_thresholds_gy,
        DEFAULT_THRESHOLDS_GY,
        lower=0.0,
        lower_inclusive=True,
        upper=MAX_THRESHOLD_GY,
    )

    slices, definition, struct_frame = _load_structure(config, struct_path, roi_number)
    dose_file = prepare_rt_file(config, dose_path)
    dataset = read_with_pixels(dose_file)

    try:
        if str(dataset.get("Modality", "")).strip().upper() != "RTDOSE":
            raise NotRtDoseError()
        dose_frame = str(dataset.get("FrameOfReferenceUID") or "").strip()
        if not struct_frame or struct_frame != dose_frame:
            raise FrameOfReferenceError()
        if code(dataset.get("DoseUnits"), frozenset({"GY"})) is None:
            raise UnsupportedGridError()

        orientation = np.asarray(dataset.ImageOrientationPatient, dtype=float)
        if orientation.shape != (6,) or not np.allclose(orientation, [1, 0, 0, 0, 1, 0], atol=1e-4):
            raise UnsupportedGridError()

        rows = int(dataset.Rows)
        columns = int(dataset.Columns)
        frames = int(dataset.get("NumberOfFrames", 1) or 1)
        scaling = number(dataset.DoseGridScaling)
        row_spacing = number(dataset.PixelSpacing[0])
        column_spacing = number(dataset.PixelSpacing[1])
        if (
            scaling is None
            or row_spacing is None
            or column_spacing is None
            or row_spacing <= 0
            or column_spacing <= 0
            or frames < 2
            or rows < 1
            or columns < 1
        ):
            raise UnsupportedGridError()

        offsets = np.asarray(dataset.GridFrameOffsetVector, dtype=float)
        position = np.asarray(dataset.ImagePositionPatient, dtype=float)
        if (
            offsets.shape != (frames,)
            or position.shape != (3,)
            or not np.all(np.isfinite(offsets))
            or not np.all(np.isfinite(position))
        ):
            raise UnsupportedGridError()
        steps = np.abs(np.diff(offsets))
        thickness = float(np.median(steps))
        if thickness <= 0 or not np.allclose(steps, thickness, rtol=1e-3, atol=1e-3):
            raise UnsupportedGridError()

        xs = position[0] + np.arange(columns) * column_spacing
        ys = position[1] + np.arange(rows) * row_spacing
        zs = position[2] + offsets
        raw = np.asarray(dataset.pixel_array).reshape(frames, rows, columns)
    except RtImagingMcpError:
        raise
    except Exception:
        raise NotRtDoseError() from None

    contour_z = sorted(slices)
    contour_thickness = float(np.median(np.diff(contour_z))) if len(contour_z) >= 2 else thickness
    mapping = nearest_slice_indices(zs.tolist(), contour_z, contour_thickness)

    used = sorted({index for index in mapping if index is not None})
    work = sum(
        polygon_work(xs, ys, polygon) for index in used for polygon in slices[contour_z[index]]
    )
    if work > MAX_RASTER_WORK:
        raise WorkLimitError()

    masks: dict[int, Any] = {}
    for index in used:
        mask = np.zeros((rows, columns), dtype=bool)
        for polygon in slices[contour_z[index]]:
            mask ^= polygon_mask(xs, ys, polygon)
        masks[index] = mask

    parts = []
    for frame, slice_index in enumerate(mapping):
        if slice_index is None:
            continue
        selected = raw[frame][masks[slice_index]]
        if selected.size:
            parts.append(selected)
    if not parts:
        raise NoStructureVoxelsError()
    doses = np.concatenate(parts).astype(np.float64) * scaling
    voxel_volume = column_spacing * row_spacing * thickness

    boxes = [
        (polygon.min(axis=0), polygon.max(axis=0))
        for polygons in slices.values()
        for polygon in polygons
    ]
    lows = np.min([box[0] for box in boxes], axis=0)
    highs = np.max([box[1] for box in boxes], axis=0)
    margin = _TOLERANCE_MM
    inside_grid = bool(
        lows[0] >= xs[0] - column_spacing / 2 - margin
        and highs[0] <= xs[-1] + column_spacing / 2 + margin
        and lows[1] >= ys[0] - row_spacing / 2 - margin
        and highs[1] <= ys[-1] + row_spacing / 2 + margin
        and contour_z[0] - contour_thickness / 2 >= zs.min() - thickness / 2 - margin
        and contour_z[-1] + contour_thickness / 2 <= zs.max() + thickness / 2 + margin
    )

    contour_volume = None
    if len(contour_z) >= 2:
        area = sum(net_slice_area(slices[z]) for z in contour_z)
        contour_volume = round(area * contour_thickness / 1000.0, 3)

    name = standardize_roi_name(definition.get("ROIName"), config.extra_roi_names)
    return {
        "roi_number": roi_number,
        "name": name,
        "name_redacted": name is None,
        "dose_units": "GY",
        "voxel_count": int(len(doses)),
        "volume_cm3": round(len(doses) * voxel_volume / 1000.0, 3),
        "contour_volume_cm3": contour_volume,
        "inside_grid": inside_grid,
        **dvh_metrics(doses, voxel_volume, percentages, thresholds),
        "method_notes": list(METHOD_NOTES),
    }
