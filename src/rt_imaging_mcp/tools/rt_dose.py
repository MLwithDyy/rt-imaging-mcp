"""RT dose tool: summary of an RTDOSE grid.

Returns grid geometry and dose statistics only. The position of the grid in patient
space, referenced plan or structure UIDs and all free text are never returned. The
dose array itself is read to compute statistics but is never returned (rules R2, R11).
"""

from __future__ import annotations

from typing import Any

import numpy as np

from rt_imaging_mcp.config import Config
from rt_imaging_mcp.security.errors import NotRtDoseError, RtImagingMcpError
from rt_imaging_mcp.tools.rt_common import code, number, prepare_rt_file, read_with_pixels

DOSE_UNITS = frozenset({"GY", "RELATIVE"})
DOSE_TYPES = frozenset({"PHYSICAL", "EFFECTIVE", "ERROR"})
DOSE_SUMMATION_TYPES = frozenset(
    {
        "PLAN",
        "MULTI_PLAN",
        "FRACTION",
        "BEAM",
        "BRACHY",
        "FRACTION_SESSION",
        "BEAM_SESSION",
        "BRACHY_SESSION",
        "CONTROL_POINT",
        "RECORD",
    }
)


def _slice_spacing(offsets: Any, frames: int) -> tuple[float | None, bool | None]:
    """Median slice spacing in mm and whether the spacing is uniform."""
    if frames < 2 or offsets is None:
        return None, None
    try:
        values = np.asarray(offsets, dtype=float)
    except (TypeError, ValueError):
        return None, None
    if values.shape != (frames,) or not np.all(np.isfinite(values)):
        return None, None
    steps = np.abs(np.diff(values))
    spacing = float(np.median(steps))
    if spacing <= 0:
        return None, None
    return round(spacing, 4), bool(np.allclose(steps, steps[0], rtol=1e-3, atol=1e-3))


def rt_dose_summary(config: Config, path: str) -> dict[str, Any]:
    """Summarise an RTDOSE file: dose type and units, grid size, voxel size, dose statistics.

    ``max_dose`` and ``mean_dose`` are in ``dose_units`` (Gy or relative) over the whole grid,
    which usually includes voxels outside the patient. They are not structure doses.
    """
    file = prepare_rt_file(config, path)
    dataset = read_with_pixels(file)
    try:
        if str(dataset.get("Modality", "")).strip().upper() != "RTDOSE":
            raise NotRtDoseError()

        rows = int(dataset.Rows)
        columns = int(dataset.Columns)
        frames = int(dataset.get("NumberOfFrames", 1) or 1)
        scaling = number(dataset.DoseGridScaling)
        if scaling is None or rows < 1 or columns < 1 or frames < 1:
            raise NotRtDoseError()

        raw = np.asarray(dataset.pixel_array).reshape(frames, rows, columns)
        total_voxels = int(raw.size)
        max_dose = float(raw.max()) * scaling
        mean_dose = float(raw.mean(dtype=np.float64)) * scaling
        above_zero = int(np.count_nonzero(raw))

        pixel_spacing = dataset.get("PixelSpacing")
        row_spacing = column_spacing = None
        if pixel_spacing is not None and len(pixel_spacing) == 2:
            row_spacing = number(pixel_spacing[0])
            column_spacing = number(pixel_spacing[1])
        slice_spacing, uniform = _slice_spacing(dataset.get("GridFrameOffsetVector"), frames)
    except RtImagingMcpError:
        raise
    except Exception:
        raise NotRtDoseError() from None

    return {
        "dose_units": code(dataset.get("DoseUnits"), DOSE_UNITS),
        "dose_type": code(dataset.get("DoseType"), DOSE_TYPES),
        "dose_summation_type": code(dataset.get("DoseSummationType"), DOSE_SUMMATION_TYPES),
        "grid": {
            "frames": frames,
            "rows": rows,
            "columns": columns,
            "total_voxels": total_voxels,
        },
        "voxel_size_mm": {
            "row": row_spacing,
            "column": column_spacing,
            "slice": slice_spacing,
            "uniform_slice_spacing": uniform,
        },
        "dose_grid_scaling": scaling,
        "max_dose": round(max_dose, 6),
        "mean_dose": round(mean_dose, 6),
        "voxels_above_zero": above_zero,
    }
