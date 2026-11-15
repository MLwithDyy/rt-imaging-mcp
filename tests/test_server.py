"""End-to-end through the MCP server object: what a client actually sees (R1, R2, R4, R6, R7)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from rt_imaging_mcp.config import Config
from rt_imaging_mcp.server import build_parser, config_from_args, create_server
from tests.synthetic import IDENTIFYING_VALUES, write_dicom, write_nifti

EXPECTED_TOOLS = {
    "dicom_scan_directory",
    "dicom_get_metadata",
    "dicom_list_allowed_tags",
    "nifti_info",
}


def call(server: MCPServer, name: str, arguments: dict[str, Any]) -> Any:
    return asyncio.run(server.call_tool(name, arguments))


def result_text(result: Any) -> str:
    return "".join(getattr(block, "text", "") for block in result.content) + json.dumps(
        result.structured_content, default=str
    )


def _visible_chain(error: BaseException) -> list[BaseException]:
    """Exceptions a printed traceback would show: causes, and contexts unless suppressed."""
    chain: list[BaseException] = []
    current: BaseException | None = error
    while current is not None and current not in chain:
        chain.append(current)
        if current.__cause__ is not None:
            current = current.__cause__
        elif not current.__suppress_context__:
            current = current.__context__
        else:
            current = None
    return chain


@pytest.fixture
def server(root: Path) -> MCPServer:
    (root / "PatientFolderBudi").mkdir()
    write_dicom(root / "PatientFolderBudi" / "IM0001")
    write_nifti(root / "vol")
    return create_server(Config.from_root(root))


def test_exactly_the_expected_tools_are_exposed(server: MCPServer) -> None:
    names = {tool.name for tool in asyncio.run(server.list_tools())}
    assert names == EXPECTED_TOOLS


def test_all_tools_declare_read_only(server: MCPServer) -> None:
    for tool in asyncio.run(server.list_tools()):
        assert tool.annotations is not None
        assert tool.annotations.read_only_hint is True
        assert tool.annotations.destructive_hint is False
        assert tool.annotations.open_world_hint is False


def test_no_tool_output_contains_identifiers_or_pixels(server: MCPServer, root: Path) -> None:
    outputs = [
        call(server, "dicom_scan_directory", {}),
        call(server, "dicom_scan_directory", {"opaque_paths": True}),
        call(server, "dicom_get_metadata", {"path": "PatientFolderBudi/IM0001"}),
        call(server, "dicom_list_allowed_tags", {}),
        call(server, "nifti_info", {"path": "vol.nii"}),
    ]
    for output in outputs:
        text = result_text(output)
        for value in IDENTIFYING_VALUES:
            assert value not in text
        assert str(root) not in text
        assert len(text) < 10_000


def test_error_results_are_static_and_do_not_leak(server: MCPServer, root: Path) -> None:
    cases = [
        ("dicom_scan_directory", {"directory": "../x"}),
        ("dicom_scan_directory", {"directory": "SecretPatientName"}),
        ("dicom_get_metadata", {"path": "PatientFolderBudi/IM0001", "keywords": ["PatientName"]}),
        ("dicom_get_metadata", {"path": "vol.nii"}),
        ("nifti_info", {"path": "PatientFolderBudi/IM0001"}),
    ]
    for name, arguments in cases:
        with pytest.raises(ToolError) as info:
            call(server, name, arguments)
        message = str(info.value)
        assert str(root) not in message
        assert "SecretPatientName" not in message
        for value in IDENTIFYING_VALUES:
            assert value not in message


def test_unexpected_exceptions_are_replaced_by_a_static_message(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rt_imaging_mcp.tools import dicom

    def boom(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("SECRET-PATIENT-NAME-IN-LIBRARY-ERROR")

    monkeypatch.setattr(dicom, "dicom_list_allowed_tags", boom)
    server = create_server(Config.from_root(root))
    with pytest.raises(ToolError) as info:
        call(server, "dicom_list_allowed_tags", {})
    assert "SECRET" not in str(info.value)
    assert "internal error" in str(info.value)
    # Everything a traceback would display must be free of the original exception.
    for error in _visible_chain(info.value):
        assert "SECRET" not in str(error)
        assert not isinstance(error, RuntimeError)


def test_server_works_through_scan_then_metadata(server: MCPServer) -> None:
    scan = call(server, "dicom_scan_directory", {}).structured_content
    first_file = scan["series"][0]["first_file"]
    meta = call(server, "dicom_get_metadata", {"path": first_file}).structured_content
    assert meta["metadata"]["Modality"] == "CT"


def test_parser_has_no_default_root(monkeypatch: pytest.MonkeyPatch) -> None:
    from rt_imaging_mcp.config import ENV_ROOT
    from rt_imaging_mcp.security.errors import ConfigError

    monkeypatch.delenv(ENV_ROOT, raising=False)
    with pytest.raises(ConfigError):
        config_from_args(build_parser().parse_args([]))


def test_parser_rejects_unknown_or_blocked_opt_in_tags(root: Path) -> None:
    from rt_imaging_mcp.security.errors import ConfigError

    for tag in ("PatientName", "NotARealTag"):
        args = build_parser().parse_args(["--root", str(root), "--enable-tag", tag])
        with pytest.raises(ConfigError):
            config_from_args(args)


def test_parser_accepts_valid_opt_in_tag(root: Path) -> None:
    args = build_parser().parse_args(["--root", str(root), "--enable-tag", "StudyDescription"])
    config = config_from_args(args)
    assert config.enabled_opt_in_tags == frozenset({"StudyDescription"})
    assert config.root == root


def test_main_exits_without_root(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from rt_imaging_mcp.config import ENV_ROOT
    from rt_imaging_mcp.server import main

    monkeypatch.delenv(ENV_ROOT, raising=False)
    with pytest.raises(SystemExit) as info:
        main([])
    assert info.value.code == 2
    assert "Provide --root" in capsys.readouterr().err
