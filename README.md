# rt-imaging-mcp

[![CI](https://github.com/MLwithDyy/rt-imaging-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/MLwithDyy/rt-imaging-mcp/actions/workflows/ci.yml)

[![RT Imaging MCP server](https://mcprush.com/badge/rt-imaging-mcp/card.svg)](https://mcprush.com/to/rt-imaging-mcp?ref=badge)

<!-- mcp-name: io.github.MLwithDyy/rt-imaging-mcp -->

A local, read-only [Model Context Protocol](https://modelcontextprotocol.io) server that lets AI agents
inspect medical image files (DICOM, NIfTI) on your own disk, with PHI-safe output by default.

> **Status: early development (pre-alpha).** DICOM scanning, allowlisted DICOM metadata, NIfTI header
> information, RTSTRUCT, RTDOSE and RTPLAN summaries and approximate dose-volume metrics work today. Radiomics is planned,
> not implemented. Dose-volume results are validated on synthetic phantoms only, not against a planning system.

## Read this first

- **Research use only. Not a medical device. Not for clinical use.**
- Running locally does **not** by itself keep data private. Tool output is sent to the model your MCP client
  uses. If that model is hosted in the cloud, so is every tool result. This project limits what tools return
  (see [docs/threat-model.md](docs/threat-model.md)) but cannot guarantee anonymity.
- For full privacy, use a locally hosted model. Never use real patient data for development or testing.

## Tools

| Tool | What it returns |
|---|---|
| `dicom_scan_directory` | Inventory of DICOM series below a directory: opaque series ids, modality, instance counts, image size, file counts. No UIDs. |
| `dicom_get_metadata` | Allowlisted technical attributes of one DICOM file (geometry, bit depth, modality, transfer syntax, ...). |
| `dicom_list_allowed_tags` | The attribute keywords `dicom_get_metadata` may currently return. |
| `nifti_info` | Shape, voxel size, data type, units and orientation from the NIfTI header. Free-text header fields are never returned. |
| `rt_dose_summary` | RTDOSE grid: dose type and units, grid size, voxel size, whole-grid maximum and mean dose, non-zero voxel count. No dose array, no grid position. |
| `rt_plan_summary` | RTPLAN: intent, approval status, fractions, one entry per beam (type, radiation, energy, angles, dose, meterset) and prescription doses. No plan, beam or machine names. |
| `rt_dvh_metrics` | Dose statistics, D(p) and V(t) for one structure of an RTSTRUCT on an RTDOSE grid (for example D95, D2, V20 Gy). Approximate; refuses mismatched frames of reference. |
| `rt_structure_summary` | One entry per RTSTRUCT structure: interpreted type, contour and slice counts, extent, approximate planar volume. Names are returned only if standard (TG-263 style), otherwise `null`. |

All tools are read-only and are declared as such to the client.

## Safety design

- **Tag allowlist.** Only listed attributes can be returned. Patient name, ID, birth date, institution, physician names,
  accession number, private tags and similar are blocked and cannot be enabled. Dates, descriptions and UIDs are
  off by default and need an explicit `--enable-tag` by the human operator (not the agent).
- **Structure names are standardised.** RTSTRUCT names are free text and can contain identifiers, so only standard
  names (a TG-263-style subset) and fixed-token target names such as `PTV_High` are returned; others are `null`.
- **RT dose and plan output is numbers and enumerated codes only.** Plan, beam and machine names, reviewer names and
  other free text are never returned.
- **Dose-volume metrics refuse inconsistent input.** The structure set and dose must share a frame of reference and
  use a supported grid; results are labelled approximate and computation is bounded.
- **No pixel data**, ever (the dose grid is read to compute statistics and is never returned).
- **One root directory.** The server refuses to start without `--root` (or `RT_IMAGING_MCP_ROOT`). `..`, absolute paths
  outside the root and symlinks that leave the root are rejected.
- **Static error messages.** Errors never quote data read from files.
- **Bounded work.** Limits on file count, directory depth and file size.
- **No writes, no network.** Enforced by a static test on the source.

Known limits are listed in the threat model. In short: file and folder names are controlled by you and can contain
identifiers (use `opaque_paths=true` to omit them), and prompt injection through file content cannot be fully prevented.

## Validation

Dose-volume metrics are checked against hand-calculated phantoms, against dicompyler-core on synthetic data, and
against dicompyler-core on three patients of one public collection (preliminary: volume, mean dose, D50 and D2
agree on all 39 structures within the stated tolerances; a few D95 and V(t) differences are unexplained).
They are **not** validated against a treatment planning system.
See [docs/validation.md](docs/validation.md) for the numbers, the differences and how to reproduce them.
The story of how two bias bugs in the dose-volume code were found (in Indonesian): [docs/validation-story.md](docs/validation-story.md).

## Install and run

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

### Install from PyPI

```bash
uvx rt-imaging-mcp --root /path/to/de-identified/images
```

For Claude Code:

```bash
claude mcp add rt-imaging -- uvx rt-imaging-mcp --root /path/to/images
```

### Install from source

```bash
git clone [https://github.com/MLwithDyy/rt-imaging-mcp](https://github.com/MLwithDyy/rt-imaging-mcp)
cd rt-imaging-mcp
uv sync
uv run rt-imaging-mcp --root /path/to/de-identified/images
```

Options: `--enable-tag KEYWORD` (repeatable, opt-in DICOM attributes), `--enable-roi-name NAME` (repeatable, extra
structure names to return), `--max-files`, `--max-depth`, `--max-file-mb`.

### Claude Code (from source)

```bash
claude mcp add rt-imaging -- uv run --directory /path/to/rt-imaging-mcp rt-imaging-mcp --root /path/to/images
```

### Claude Desktop (and other clients using a JSON config)

```json
{
  "mcpServers": {
    "rt-imaging": {
      "command": "uv",
      "args": [
        "run", "--directory", "/path/to/rt-imaging-mcp",
        "rt-imaging-mcp", "--root", "/path/to/images"
      ]
    }
  }
}
```

On Windows, escape backslashes in JSON (`D:\\Project\\rt-imaging-mcp`) or use forward slashes.

Debug with the MCP Inspector:

```bash
npx @modelcontextprotocol/inspector uv run rt-imaging-mcp --root /path/to/images
```

## Development

```bash
uv sync
uv run pytest
uv run ruff check .
uv run mypy
pre-commit install
```

Tests use synthetic data generated at run time. Medical image files are blocked from commits by `.gitignore`
and a pre-commit hook. Do not attach real patient data to issues or pull requests.

## Roadmap

1. DICOM and NIfTI basics (done, pre-alpha)
2. CI on Python 3.11-3.13, Linux and Windows (done)
3. Radiotherapy objects: RTSTRUCT, RTDOSE and RTPLAN summaries and approximate DVH metrics (done)
4. Radiomics feature extraction with validation against IBSI reference data
5. Release to PyPI (done)

## Related work

- [`dicom-mcp`](https://github.com/ChristianHinge/dicom-mcp) connects agents to DICOM network servers (PACS). This project
  is complementary: it works on local files and focuses on PHI-safe output, radiotherapy objects and radiomics.
- [`rt-qa-agent`](https://github.com/MLwithDyy/rt-qa-agent) is a reference downstream radiotherapy QA audit agent built on
  `rt-imaging-mcp`, pairing its read-only DICOM/DVH tools with YAML clinical protocols (`RTOG 0813`, `EMBRACE-II`, `RTOG 1016`)
  and deterministic dose-constraint checks.

## Contributing and security

See [CONTRIBUTING.md](CONTRIBUTING.md). Never attach real patient data to issues or pull requests.
Report vulnerabilities privately as described in [SECURITY.md](SECURITY.md).

## License

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).