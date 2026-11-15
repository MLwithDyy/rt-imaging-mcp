"""NIfTI tool: structural information from the header only.

Free-text header fields (``descrip``, ``aux_file``, ``db_name``) can contain
identifiers and are never returned. The image data array is never loaded (R2).
"""

from __future__ import annotations

import math
from typing import Any

import nibabel as nib

from rt_imaging_mcp.config import Config
from rt_imaging_mcp.security.errors import FileTooLargeError, NotNiftiError
from rt_imaging_mcp.security.paths import resolve_in_root


def _finite(value: float) -> float | None:
    return value if math.isfinite(value) else None


def nifti_info(config: Config, path: str) -> dict[str, Any]:
    """Return shape, voxel size, data type, units and orientation of a NIfTI file."""
    file = resolve_in_root(config.root, path, kind="file")
    if file.stat().st_size > config.max_file_bytes:
        raise FileTooLargeError()

    try:
        image = nib.load(str(file))
        if not isinstance(image, nib.Nifti1Image | nib.Nifti2Image):
            raise NotNiftiError()
        header = image.header
        shape = [int(size) for size in image.shape]
        voxel_size = [_finite(float(zoom)) for zoom in header.get_zooms()]
        space_unit, time_unit = header.get_xyzt_units()
        orientation = "".join(code or "?" for code in nib.aff2axcodes(image.affine))
        data_type = str(header.get_data_dtype())
        file_format = "NIfTI-2" if isinstance(image, nib.Nifti2Image) else "NIfTI-1"
    except NotNiftiError:
        raise
    except Exception:
        raise NotNiftiError() from None

    voxel_count = 1
    for size in shape:
        voxel_count *= size

    return {
        "format": file_format,
        "shape": shape,
        "ndim": len(shape),
        "voxel_count": voxel_count,
        "data_type": data_type,
        "voxel_size": voxel_size,
        "space_unit": space_unit or None,
        "time_unit": time_unit or None,
        "orientation": orientation,
    }
