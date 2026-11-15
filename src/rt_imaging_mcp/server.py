"""MCP server wiring.

Every tool is wrapped by ``_guard`` so that clients only ever see static error
messages (rule R6), even when a library raises an exception whose text contains
data read from a file.
"""

from __future__ import annotations

import argparse
import functools
import sys
from collections.abc import Callable, Sequence
from typing import Any, TypeVar

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from rt_imaging_mcp import __version__
from rt_imaging_mcp.config import ENV_ROOT, Config
from rt_imaging_mcp.security.allowlist import OPT_IN_KEYWORDS
from rt_imaging_mcp.security.errors import ConfigError, RtImagingMcpError
from rt_imaging_mcp.tools import dicom, nifti, rt, rt_dose, rt_dvh, rt_plan

INSTRUCTIONS = (
    "Read-only access to local medical image files (DICOM, NIfTI) below one configured "
    "root directory. Output is deliberately minimal: patient identifiers, pixel data and "
    "absolute paths are never returned. Do not try to retrieve identifying information. "
    "Research use only; not for clinical decisions."
)

_READ_ONLY = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)

F = TypeVar("F", bound=Callable[..., Any])


def _guard(function: F) -> F:
    """Convert every failure into a ToolError with a static message."""

    @functools.wraps(function)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return function(*args, **kwargs)
        except RtImagingMcpError as error:
            raise ToolError(str(error)) from None
        except Exception:
            raise ToolError("internal error") from None

    return wrapper  # type: ignore[return-value]


def create_server(config: Config) -> MCPServer:
    """Build the MCP server for one configured root."""
    server = MCPServer("rt-imaging-mcp", version=__version__, instructions=INSTRUCTIONS)

    @server.tool(
        name="dicom_scan_directory",
        title="Scan a directory for DICOM series",
        annotations=_READ_ONLY,
    )
    @_guard
    def dicom_scan_directory(directory: str = ".", opaque_paths: bool = False) -> dict[str, Any]:
        """Inventory DICOM series below a directory (path relative to the root).

        Returns opaque series ids, modality, instance counts and image size. Study and
        series UIDs are never returned. Set opaque_paths=True to omit all file and
        directory names. Only DICOM Part 10 files (with the DICM preamble) are detected.
        """
        return dicom.dicom_scan_directory(config, directory, opaque_paths)

    @server.tool(
        name="dicom_get_metadata",
        title="Read allowlisted DICOM metadata",
        annotations=_READ_ONLY,
    )
    @_guard
    def dicom_get_metadata(path: str, keywords: list[str] | None = None) -> dict[str, Any]:
        """Read allowlisted technical attributes of one DICOM file (path relative to the root).

        Use dicom_list_allowed_tags to see which keywords are allowed. Requesting any other
        keyword fails. Patient identifiers and pixel data are never returned.
        """
        return dicom.dicom_get_metadata(config, path, keywords)

    @server.tool(
        name="dicom_list_allowed_tags",
        title="List allowed DICOM attribute keywords",
        annotations=_READ_ONLY,
    )
    @_guard
    def dicom_list_allowed_tags() -> dict[str, Any]:
        """List the DICOM attribute keywords that dicom_get_metadata can currently return."""
        return dicom.dicom_list_allowed_tags(config)

    @server.tool(
        name="nifti_info",
        title="Read NIfTI header information",
        annotations=_READ_ONLY,
    )
    @_guard
    def nifti_info(path: str) -> dict[str, Any]:
        """Return shape, voxel size, data type, units and orientation of a NIfTI file.

        Only structural header fields are returned. Free-text header fields and the image
        data are never read into the output.
        """
        return nifti.nifti_info(config, path)

    @server.tool(
        name="rt_structure_summary",
        title="Summarise an RT structure set",
        annotations=_READ_ONLY,
    )
    @_guard
    def rt_structure_summary(path: str) -> dict[str, Any]:
        """Summarise an RTSTRUCT file (path relative to the root): one entry per structure.

        Structure names are returned only when they match a standard name (TG-263 style);
        other names are redacted. Returns interpreted type, contour and slice counts, extent
        in mm and an approximate planar-contour volume. No coordinates or free-text labels.
        """
        return rt.rt_structure_summary(config, path)

    @server.tool(
        name="rt_dose_summary",
        title="Summarise an RT dose grid",
        annotations=_READ_ONLY,
    )
    @_guard
    def rt_dose_summary(path: str) -> dict[str, Any]:
        """Summarise an RTDOSE file (path relative to the root).

        Returns dose type and units, grid size, voxel size and whole-grid dose statistics
        (maximum, mean, non-zero voxel count). No dose array, grid position or identifiers.
        """
        return rt_dose.rt_dose_summary(config, path)

    @server.tool(
        name="rt_plan_summary",
        title="Summarise an RT plan",
        annotations=_READ_ONLY,
    )
    @_guard
    def rt_plan_summary(path: str) -> dict[str, Any]:
        """Summarise an RTPLAN file (path relative to the root).

        Returns intent, approval status, fractions, one entry per beam (type, radiation,
        energy, angles, dose and meterset) and prescription doses. Plan, beam and machine
        names and other free text are never returned.
        """
        return rt_plan.rt_plan_summary(config, path)

    @server.tool(
        name="rt_dvh_metrics",
        title="Dose-volume metrics for one structure",
        annotations=_READ_ONLY,
    )
    @_guard
    def rt_dvh_metrics(
        struct_path: str,
        dose_path: str,
        roi_number: int,
        dose_percentages: list[float] | None = None,
        volume_thresholds_gy: list[float] | None = None,
    ) -> dict[str, Any]:
        """Dose statistics and D/V metrics for one structure (paths relative to the root).

        Combines an RTSTRUCT and an RTDOSE that share a frame of reference. Use
        rt_structure_summary to find roi_number. dose_percentages gives D(p), the highest dose
        that at least p percent of the volume receives (default 95, 50, 2). volume_thresholds_gy
        gives V(t), the volume receiving at least t Gy (default 20). Results are approximate
        (voxel centres, nearest contour slice) and not validated against a planning system.
        """
        return rt_dvh.rt_dvh_metrics(
            config, struct_path, dose_path, roi_number, dose_percentages, volume_thresholds_gy
        )

    return server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rt-imaging-mcp",
        description="Local, read-only MCP server for medical image files (research use only).",
    )
    parser.add_argument(
        "--root",
        help=f"Root directory the server may read. Defaults to ${ENV_ROOT}. "
        "There is no other default.",
    )
    parser.add_argument(
        "--enable-tag",
        action="append",
        default=[],
        metavar="KEYWORD",
        help="Enable an opt-in DICOM keyword (for example StudyDescription). Can be repeated. "
        "These attributes may contain identifiers; enable them only for de-identified data.",
    )
    parser.add_argument(
        "--enable-roi-name",
        action="append",
        default=[],
        metavar="NAME",
        help="Also return this structure name (exact match, case-insensitive). Can be repeated. "
        "Structure names can contain identifiers; enable names only for de-identified data.",
    )
    parser.add_argument("--max-files", type=int, default=Config.max_files)
    parser.add_argument("--max-depth", type=int, default=Config.max_depth)
    parser.add_argument("--max-file-mb", type=int, default=Config.max_file_bytes // (1024 * 1024))
    return parser


def config_from_args(args: argparse.Namespace) -> Config:
    unknown = sorted(set(args.enable_tag) - OPT_IN_KEYWORDS)
    if unknown:
        raise ConfigError()
    overrides: dict[str, Any] = {
        "max_files": args.max_files,
        "max_depth": args.max_depth,
        "max_file_bytes": args.max_file_mb * 1024 * 1024,
        "enabled_opt_in_tags": frozenset(args.enable_tag),
        "extra_roi_names": frozenset(args.enable_roi_name),
    }
    if args.root:
        return Config.from_root(args.root, **overrides)
    base = Config.from_env()
    return Config.from_root(base.root, **overrides)


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        config = config_from_args(args)
    except RtImagingMcpError as error:
        print(f"rt-imaging-mcp: {error}. Provide --root or set {ENV_ROOT}.", file=sys.stderr)
        raise SystemExit(2) from None
    create_server(config).run()


if __name__ == "__main__":
    main()
