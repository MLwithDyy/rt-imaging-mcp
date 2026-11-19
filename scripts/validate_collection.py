"""Validate ``rt_dvh_metrics`` on a folder of RT cases and print aggregate numbers only.

Meant for a few patients downloaded from a public, de-identified collection (kept OUTSIDE this
repository). For every case it pairs each RTSTRUCT with an RTDOSE that shares its frame of
reference, runs ``rt_dvh_metrics`` for structures with standard names, runs dicompyler-core on
the same files (needs ``uv`` on PATH) and compares the two.

    uv run python scripts/validate_collection.py D:\\rt-data\\COLLECTION --max-cases 5

Cases are the sub-folders of ROOT (use ``--case-depth 2`` when ROOT holds one folder per
collection with the patients inside it). Output never contains paths or patient identifiers, and
no non-standard structure names unless you enable them: cases are numbered ``case_001``,
``case_002``, ... in sorted order.

Differences between the two programs are expected (different voxel inclusion rules). What matters
is whether they are small, explained and honestly reported in docs/validation.md.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS.parent / "src"))

from compare_dvh import compare, metrics_from_result, run_reference  # noqa: E402

DEFAULT_PERCENT = [95.0, 50.0, 2.0]
DEFAULT_GY = [20.0, 40.0]


@dataclass(frozen=True)
class RtFile:
    path: Path
    modality: str  # "RTSTRUCT" or "RTDOSE"
    frame: str  # frame of reference UID (compared, never printed)
    summation: str  # DoseSummationType for RTDOSE


@dataclass
class Case:
    label: str
    structs: list[RtFile] = field(default_factory=list)
    doses: list[RtFile] = field(default_factory=list)


def read_rt_file(path: Path) -> RtFile | None:
    """Header of an RTSTRUCT or RTDOSE file, or ``None`` for anything else."""
    import pydicom

    try:
        with path.open("rb") as handle:
            handle.seek(128)
            if handle.read(4) != b"DICM":
                return None
        dataset = pydicom.dcmread(
            path,
            stop_before_pixels=True,
            specific_tags=[
                "Modality",
                "FrameOfReferenceUID",
                "ReferencedFrameOfReferenceSequence",
                "DoseSummationType",
            ],
        )
    except Exception:
        return None
    modality = str(dataset.get("Modality", "")).strip().upper()
    if modality == "RTSTRUCT":
        sequence = dataset.get("ReferencedFrameOfReferenceSequence") or []
        frame = str(sequence[0].get("FrameOfReferenceUID", "")) if len(sequence) else ""
        return RtFile(path, modality, frame.strip(), "")
    if modality == "RTDOSE":
        frame = str(dataset.get("FrameOfReferenceUID", "") or "")
        summation = str(dataset.get("DoseSummationType", "")).strip().upper()
        return RtFile(path, modality, frame.strip(), summation)
    return None


def case_directories(root: Path, depth: int) -> list[Path]:
    """Directories exactly ``depth`` levels below ``root``, in sorted order."""
    level = [root]
    for _ in range(depth):
        level = [child for parent in level for child in sorted(parent.iterdir()) if child.is_dir()]
    return level


def discover(root: Path, case_depth: int, max_cases: int | None) -> list[Case]:
    """Cases that contain both an RTSTRUCT and an RTDOSE, labelled in sorted order."""
    cases: list[Case] = []
    for directory in case_directories(root, case_depth):
        structs: list[RtFile] = []
        doses: list[RtFile] = []
        for dirpath, dirnames, filenames in os.walk(directory):
            dirnames.sort()
            for name in sorted(filenames):
                found = read_rt_file(Path(dirpath) / name)
                if found is None:
                    continue
                (structs if found.modality == "RTSTRUCT" else doses).append(found)
        if structs and doses:
            cases.append(Case(f"case_{len(cases) + 1:03d}", structs, doses))
            if max_cases is not None and len(cases) >= max_cases:
                break
    return cases


def pair_files(case: Case, max_pairs: int) -> tuple[list[tuple[RtFile, RtFile]], int]:
    """RTSTRUCT/RTDOSE pairs sharing a frame of reference, and the number of pairs that do not.

    Plan-level doses are preferred over beam-level doses when both exist.
    """
    plan_doses = [dose for dose in case.doses if dose.summation in {"PLAN", "MULTI_PLAN"}]
    doses = plan_doses or case.doses
    matching: list[tuple[RtFile, RtFile]] = []
    mismatched = 0
    for struct in case.structs:
        for dose in doses:
            if struct.frame and struct.frame == dose.frame:
                matching.append((struct, dose))
            else:
                mismatched += 1
    return matching[:max_pairs], mismatched


def select_structures(
    summary: dict[str, Any],
    max_rois: int,
    min_volume_cm3: float,
    include_redacted: bool = False,
) -> list[dict[str, Any]]:
    """Structures with a usable volume, in ROI number order.

    By default only structures whose name is returned (a standard name, or one enabled with
    ``--enable-roi-name``) are chosen. ``include_redacted`` also takes structures with redacted
    names, which are then reported by ROI number only.
    """
    chosen = [
        roi
        for roi in summary["rois"]
        if (include_redacted or roi["name"] is not None)
        and (roi["approx_volume_cm3"] or 0.0) >= min_volume_cm3
    ]
    return chosen[:max_rois]


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Per-metric statistics of the absolute differences over all compared structures."""
    differences: dict[str, list[float]] = {}
    exceeding: Counter[str] = Counter()
    for row in rows:
        for entry in row["comparison"]:
            differences.setdefault(entry["metric"], []).append(abs(entry["difference"]))
            if entry["exceeds"]:
                exceeding[entry["metric"]] += 1
    metrics = {
        metric: {
            "n": len(values),
            "median_abs_difference": round(statistics.median(values), 4),
            "max_abs_difference": round(max(values), 4),
            "exceeding_tolerance": exceeding[metric],
        }
        for metric, values in sorted(differences.items())
    }
    return {"compared_structures": len(rows), "metrics": metrics}


def volume_class(volume_cm3: float, edges: list[float]) -> str:
    """Label of the size class ``volume_cm3`` falls in, for example ``"20-200 cm3"``."""
    bounds = [0.0, *edges, float("inf")]
    for low, high in zip(bounds, bounds[1:], strict=False):
        if low <= volume_cm3 < high:
            return (
                f"<{high:g} cm3"
                if low == 0.0
                else (f">={low:g} cm3" if high == float("inf") else f"{low:g}-{high:g} cm3")
            )
    return "unclassified"


def summarize_by_volume(rows: list[dict[str, Any]], edges: list[float]) -> dict[str, Any]:
    """The aggregate summary computed separately for each structure size class."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(volume_class(row["volume_cm3"], edges), []).append(row)
    return {label: summarize(group) for label, group in sorted(groups.items())}


def run_case_pair(
    root: Path,
    label: str,
    struct: RtFile,
    dose: RtFile,
    args: argparse.Namespace,
    refusals: Counter[str],
) -> list[dict[str, Any]]:
    from rt_imaging_mcp.config import Config
    from rt_imaging_mcp.security.errors import RtImagingMcpError
    from rt_imaging_mcp.tools.rt import rt_structure_summary
    from rt_imaging_mcp.tools.rt_dvh import rt_dvh_metrics

    config = Config.from_root(root, extra_roi_names=frozenset(args.enable_roi_name))
    struct_path = str(struct.path.relative_to(root))
    dose_path = str(dose.path.relative_to(root))
    try:
        summary = rt_structure_summary(config, struct_path)
    except RtImagingMcpError as error:
        refusals[f"rt_structure_summary: {error}"] += 1
        return []

    ours: dict[int, tuple[dict[str, Any], dict[str, float]]] = {}
    for roi in select_structures(
        summary, args.max_rois, args.min_volume_cm3, args.include_redacted
    ):
        try:
            result = rt_dvh_metrics(
                config, struct_path, dose_path, roi["roi_number"], args.percent, args.gy
            )
        except RtImagingMcpError as error:
            refusals[f"rt_dvh_metrics: {error}"] += 1
            continue
        ours[roi["roi_number"]] = (result, metrics_from_result(result))
    if not ours:
        return []

    completed = run_reference(struct.path, dose.path, sorted(ours), args.percent, args.gy)
    if completed.returncode != 0:
        refusals["dicompyler-core: reference run failed"] += 1
        if args.debug_reference:  # stderr can contain file paths: never paste it anywhere unedited
            sys.stderr.write(completed.stderr[-1500:] + "\n")
        return []
    parsed = json.loads(completed.stdout.strip().splitlines()[-1])
    if len(ours) == 1:  # single-structure runs print a flat object
        parsed = {str(next(iter(ours))): parsed}

    rows: list[dict[str, Any]] = []
    for number, (result, metrics) in sorted(ours.items()):
        reference = parsed.get(str(number), {})
        if "error" in reference or not reference:
            refusals["dicompyler-core: structure failed"] += 1
            continue
        rows.append(
            {
                "case": label,
                "roi_number": number,
                "name": result["name"],
                "inside_grid": result["inside_grid"],
                "voxels": result["voxel_count"],
                "volume_cm3": result["volume_cm3"],
                "voxel_mm": result["voxel_size_mm"],
                "contour_dz_mm": result["contour_slice_spacing_mm"],
                "comparison": compare(
                    metrics, reference, args.tolerance_gy, args.tolerance_percent
                ),
            }
        )
    return rows


def format_rows(rows: list[dict[str, Any]], show: tuple[str, ...]) -> str:
    header = (
        f"{'case':<10}{'roi':>4}  {'name':<12}{'voxels':>8}{'voxel mm':>14}{'cdz':>6}  "
        + "".join(f"{metric:>10}" for metric in show)
    )
    lines = [header, "-" * len(header)]
    for row in rows:
        by_metric = {entry["metric"]: entry for entry in row["comparison"]}
        cells = []
        for metric in show:
            entry = by_metric.get(metric)
            cells.append(
                f"{entry['difference']:>+9.3f}{'*' if entry['exceeds'] else ' '}"
                if entry
                else f"{'-':>10}"
            )
        voxel = row["voxel_mm"]
        voxel_text = f"{voxel['row']:g}x{voxel['column']:g}x{voxel['slice']:g}"
        contour_dz = row["contour_dz_mm"]
        contour_text = f"{contour_dz:g}" if contour_dz is not None else "-"
        lines.append(
            f"{row['case']:<10}{row['roi_number']:>4}  {row['name'] or '(redacted)':<12}"
            f"{row['voxels']:>8}{voxel_text:>14}{contour_text:>6}  " + "".join(cells)
        )
    lines.append("(differences: ours - dicompyler-core; * = beyond tolerance)")
    return "\n".join(lines)


def format_summary(summary: dict[str, Any]) -> str:
    lines = [f"structures compared: {summary['compared_structures']}"]
    lines.append(
        f"{'metric':<16}{'n':>5}{'median |diff|':>16}{'max |diff|':>13}{'beyond tol.':>13}"
    )
    for metric, values in summary["metrics"].items():
        lines.append(
            f"{metric:<16}{values['n']:>5}{values['median_abs_difference']:>16.4f}"
            f"{values['max_abs_difference']:>13.4f}{values['exceeding_tolerance']:>13}"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("root", type=Path)
    parser.add_argument("--case-depth", type=int, default=1)
    parser.add_argument("--max-cases", type=int, default=5)
    parser.add_argument("--max-pairs-per-case", type=int, default=1)
    parser.add_argument("--max-rois", type=int, default=8)
    parser.add_argument("--min-volume-cm3", type=float, default=1.0)
    parser.add_argument(
        "--enable-roi-name",
        action="append",
        default=[],
        metavar="NAME",
        help="also treat this structure name as returnable (repeatable). Only for public, "
        "de-identified data; the name is then printed.",
    )
    parser.add_argument(
        "--include-redacted",
        action="store_true",
        help="also compare structures whose names are redacted (reported by ROI number only)",
    )
    parser.add_argument("--percent", type=float, nargs="*", default=DEFAULT_PERCENT)
    parser.add_argument("--gy", type=float, nargs="*", default=DEFAULT_GY)
    parser.add_argument(
        "--size-edges",
        type=float,
        nargs="*",
        default=[20.0, 200.0],
        help="structure volume class boundaries in cm3 for the per-size summary",
    )
    parser.add_argument("--tolerance-gy", type=float, default=0.1)
    parser.add_argument("--tolerance-percent", type=float, default=2.0)
    parser.add_argument("--json-out", type=Path, help="write rows and summary (numbers only)")
    parser.add_argument(
        "--debug-reference",
        action="store_true",
        help="print the end of the dicompyler-core error output to your terminal (it may contain "
        "file paths; do not paste it anywhere without removing them)",
    )
    args = parser.parse_args()

    root = args.root.resolve()
    cases = discover(root, args.case_depth, args.max_cases)
    if not cases:
        raise SystemExit("no case with both an RTSTRUCT and an RTDOSE was found")

    refusals: Counter[str] = Counter()
    rows: list[dict[str, Any]] = []
    skipped_frame_pairs = 0
    pairs_run = 0
    for case in cases:
        pairs, mismatched = pair_files(case, args.max_pairs_per_case)
        skipped_frame_pairs += mismatched
        for struct, dose in pairs:
            pairs_run += 1
            rows.extend(run_case_pair(root, case.label, struct, dose, args, refusals))

    summary = summarize(rows)
    print(f"cases found: {len(cases)}, structure/dose pairs run: {pairs_run}")
    print(f"pairs skipped (frame of reference missing or different): {skipped_frame_pairs}")
    if rows:
        shown = ("volume_cm3", "mean", "D95", "D50", "D2")
        print()
        print(format_rows(rows, shown))
        print()
        print(format_summary(summary))
        by_size = summarize_by_volume(rows, args.size_edges)
        for label, group in by_size.items():
            print(f"\nstructure volume {label}:")
            print(format_summary(group))
    if refusals:
        print("\nrefused or failed (count: reason):")
        for reason, count in refusals.most_common():
            print(f"  {count}: {reason}")
    if args.json_out:
        payload = {
            "rows": rows,
            "summary": summary,
            "by_volume_class": summarize_by_volume(rows, args.size_edges),
            "refusals": dict(refusals),
        }
        args.json_out.write_text(json.dumps(payload, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
