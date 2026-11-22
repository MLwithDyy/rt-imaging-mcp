"""MCP registry metadata: the README marker, server.json and the package version must agree.

These tests only run when a ``server.json`` exists in the repository root, so they cost nothing
until the project is registered. Once it is, CI fails if the version, the registry name or the
README ownership marker drift apart (the registry rejects a package whose README does not carry
the matching ``mcp-name`` marker).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

import rt_imaging_mcp

REPO = Path(__file__).resolve().parents[1]
SERVER_JSON = REPO / "server.json"
MARKER = re.compile(r"mcp-name:\s*([A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+)")

pytestmark = pytest.mark.skipif(
    not SERVER_JSON.is_file(), reason="server.json is not part of this checkout"
)


def load() -> dict[str, Any]:
    data = json.loads(SERVER_JSON.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def test_readme_carries_exactly_one_marker_matching_the_server_name() -> None:
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    assert MARKER.findall(readme) == [load()["name"]]


def test_server_name_is_a_github_namespaced_name_with_one_slash() -> None:
    name = load()["name"]
    assert name.count("/") == 1
    assert name.startswith("io.github.")
    assert 3 <= len(name) <= 200


def test_description_fits_the_registry_limit() -> None:
    assert 1 <= len(load()["description"]) <= 100


def test_versions_match_the_package_version() -> None:
    data = load()
    version = rt_imaging_mcp.__version__
    assert data["version"] == version
    for package in data.get("packages", []):
        assert package["version"] == version


def test_the_pypi_package_is_the_one_this_project_publishes() -> None:
    identifiers = [package.get("identifier") for package in load().get("packages", [])]
    assert "rt-imaging-mcp" in identifiers


def test_repository_points_at_this_project() -> None:
    assert "MLwithDyy/rt-imaging-mcp" in load()["repository"]["url"]
