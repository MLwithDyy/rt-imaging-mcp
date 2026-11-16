# Changelog

All notable changes are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/). While the major version is 0, anything may change.

## [Unreleased]

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
- Scripts to compare dose-volume metrics with dicompyler-core on synthetic phantoms.

### Known limits

- Dose-volume metrics are validated on synthetic phantoms and against dicompyler-core on those phantoms only,
  not against a treatment planning system or real patient data. See [docs/validation.md](docs/validation.md).
