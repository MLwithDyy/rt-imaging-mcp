# rt-imaging-mcp

[![CI](https://github.com/MLwithDyy/rt-imaging-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/MLwithDyy/rt-imaging-mcp/actions/workflows/ci.yml)

A local, read-only [Model Context Protocol](https://modelcontextprotocol.io) server that lets AI agents
inspect medical image files (DICOM, NIfTI) on your own disk, with PHI-safe output by default.

> **Status: early development (pre-alpha).** DICOM scanning, allowlisted DICOM metadata, NIfTI header
> information and RTSTRUCT summaries work today. RTDOSE, RTPLAN, DVH metrics and radiomics are planned, not implemented.

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
| `rt_structure_summary` | One entry per RTSTRUCT structure: interpreted type, contour and slice counts, extent, approximate planar volume. Names are returned only if standard (TG-263 style), otherwise `null`. |

All tools are read-only and are declared as such to the client.

## Safety design

- **Tag allowlist.** Only listed attributes can be returned. Patient name, ID, birth date, institution, physician names,
  accession number, private tags and similar are blocked and cannot be enabled. Dates, descriptions and UIDs are
  off by default and need an explicit `--enable-tag` by the human operator (not the agent).
- **Structure names are standardised.** RTSTRUCT names are free text and can contain identifiers, so only standard
  names (a TG-263-style subset) and fixed-token target names such as `PTV_High` are returned; others are `null`.
- **No pixel data**, ever.
- **One root directory.** The server refuses to start without `--root` (or `RT_IMAGING_MCP_ROOT`). `..`, absolute paths
  outside the root and symlinks that leave the root are rejected.
- **Static error messages.** Errors never quote data read from files.
- **Bounded work.** Limits on file count, directory depth and file size.
- **No writes, no network.** Enforced by a static test on the source.

Known limits are listed in the threat model. In short: file and folder names are controlled by you and can contain
identifiers (use `opaque_paths=true` to omit them), and prompt injection through file content cannot be fully prevented.

## Install and run

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/MLwithDyy/rt-imaging-mcp
cd rt-imaging-mcp
uv sync
uv run rt-imaging-mcp --root /path/to/de-identified/images
```

Options: `--enable-tag KEYWORD` (repeatable, opt-in DICOM attributes), `--enable-roi-name NAME` (repeatable, extra
structure names to return), `--max-files`, `--max-depth`, `--max-file-mb`.

### Claude Code

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
3. Radiotherapy objects: RTSTRUCT summary (done), RTDOSE and RTPLAN summaries, simple DVH metrics
4. Radiomics feature extraction with validation against IBSI reference data
5. Release to PyPI

## Related work

[`dicom-mcp`](https://github.com/ChristianHinge/dicom-mcp) connects agents to DICOM network servers (PACS). This project
is complementary: it works on local files and focuses on PHI-safe output, radiotherapy objects and radiomics.

## License

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
