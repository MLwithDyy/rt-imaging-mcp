"""Run the real server as a subprocess and talk to it over stdio with an MCP client."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from tests.synthetic import IDENTIFYING_VALUES, write_dicom

SRC = str(Path(__file__).resolve().parents[1] / "src")


async def _run(root: Path) -> dict[str, Any]:
    env = {**os.environ, "PYTHONPATH": SRC}
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "rt_imaging_mcp", "--root", str(root)],
        env=env,
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        tools = await session.list_tools()
        scan = await session.call_tool("dicom_scan_directory", {})
        meta = await session.call_tool("dicom_get_metadata", {"path": "scan_dir/IM0001"})
        blocked = await session.call_tool(
            "dicom_get_metadata", {"path": "scan_dir/IM0001", "keywords": ["PatientName"]}
        )
        return {"tools": tools, "scan": scan, "meta": meta, "blocked": blocked}


def test_server_over_stdio(root: Path) -> None:
    (root / "scan_dir").mkdir()
    write_dicom(root / "scan_dir" / "IM0001")

    results = asyncio.run(asyncio.wait_for(_run(root), timeout=60))

    names = {tool.name for tool in results["tools"].tools}
    assert names == {
        "dicom_scan_directory",
        "dicom_get_metadata",
        "dicom_list_allowed_tags",
        "nifti_info",
    }
    assert results["meta"].is_error is False
    assert results["scan"].is_error is False

    everything = json.dumps(
        [r.model_dump(mode="json") for r in (results["scan"], results["meta"], results["blocked"])]
    )
    for value in IDENTIFYING_VALUES:
        assert value not in everything
    assert str(root) not in everything

    assert results["blocked"].is_error is True
    assert "tag is not allowed" in everything
