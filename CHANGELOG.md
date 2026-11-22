# Changelog

All notable changes are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/). While the major version is 0, anything may change.

## [Unreleased]

## [0.1.0] - 2026-11-19

## [0.1.1] - 2026-11-22

### Added

- Read-only MCP server with stdio transport and a mandatory `--root` directory.
- DICOM tools: `dicom_scan_directory` (opaque series ids, no UIDs), `dicom_get_metadata` (tag allowlist) and
  `dicom_list_allowed_tags`.
- `nifti_info`: structural header information only.
- Radiotherapy tools: `rt_structure_summary` (standardised structure names, planar volume estimate),
  `rt_dose_summary`, `rt_plan_summary` (numbers and allowlisted codes only) and `rt_dvh_metrics` (approximate
  D(p) and V(t) for one structure).
- Operator options `--enable-tag` and `--enable-roi-name`, and limits `--max-files`, `--max-depth`, `--max-file-mb`.
- Threat model (rules R1-R12), pre-commit guard against medical image files, CI on Linux and Windows for
  Python 3.11-3.13.
- Scripts to compare dose-volume metrics with dicompyler-core on synthetic phantoms, and `validate_collection.py`
  to run the comparison over a folder of RT cases and print anonymous aggregate numbers.
- MCP registry metadata: `server.json` and the `mcp-name` ownership marker in the README.

### Changed

- `rt_dvh_metrics` also returns `voxel_size_mm` and `contour_slice_spacing_mm`, so results can be read next to the
  grid resolution. `validate_collection.py` prints the voxel size and contour spacing of every structure and
  summarises by structure size.
- Voxel weights follow the overlap of each dose slice with the contour slabs: a dose plane exactly on the outer
  boundary of a structure counts half instead of in full, and a plane exactly between two contour slices takes half
  from each instead of belonging wholly to the lower one. This removes a bias of about one plane at the structure
  ends and a bias that grew with the change of cross-section between slices (found with phantoms whose dose planes
  are twice as dense as the contour planes), and makes the structure volume equal to the sum of its slabs.
- The README documents installation from PyPI with `uvx`.

### Fixed

- `rt_dvh_metrics` refused realistic structures with `computation exceeds the work limit`: the rasteriser cost
  grew with cells times polygon edges and the cap was too low for dense manual contours on fine dose grids.
  Rasterisation now uses a scanline method (cells plus edge crossings) that gives identical masks and is far
  faster, and the work estimate reflects that.

### Known limits

- Dose-volume metrics are validated on synthetic phantoms and against dicompyler-core on those phantoms only,
  not against a treatment planning system or real patient data. See [docs/validation.md](docs/validation.md).
