"""Rule R7: the server package must not write, delete, move or send anything.

This is a static check on the source. It is a tripwire for accidental additions,
not a sandbox: it cannot prove the absence of every possible side effect.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "rt_imaging_mcp"

FORBIDDEN_IMPORTS = {
    "socket",
    "ssl",
    "http",
    "urllib",
    "urllib3",
    "requests",
    "httpx",
    "aiohttp",
    "ftplib",
    "smtplib",
    "subprocess",
    "shutil",
    "tempfile",
    "pickle",
}
FORBIDDEN_ATTRIBUTES = {
    "write_text",
    "write_bytes",
    "unlink",
    "rmdir",
    "rename",
    "mkdir",
    "touch",
    "symlink_to",
    "hardlink_to",
    "save_as",
    "remove",
    "rmtree",
    "removedirs",
    "makedirs",
    "chmod",
    "truncate",
}
FORBIDDEN_CALLS = {"eval", "exec", "compile", "__import__"}
WRITE_MODE_CHARS = set("wax+")

SOURCES = sorted(PACKAGE.rglob("*.py"))


def _imports(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


def test_sources_were_found() -> None:
    assert len(SOURCES) >= 8


@pytest.mark.parametrize("source", SOURCES, ids=lambda p: p.name)
def test_no_forbidden_imports(source: Path) -> None:
    tree = ast.parse(source.read_text(encoding="utf-8"))
    assert _imports(tree) & FORBIDDEN_IMPORTS == set()


@pytest.mark.parametrize("source", SOURCES, ids=lambda p: p.name)
def test_no_write_apis_or_dynamic_code(source: Path) -> None:
    tree = ast.parse(source.read_text(encoding="utf-8"))
    problems: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_ATTRIBUTES:
            problems.append(f"attribute {node.attr} at line {node.lineno}")
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in FORBIDDEN_CALLS:
                problems.append(f"call {func.id} at line {node.lineno}")
            is_open = (isinstance(func, ast.Name) and func.id == "open") or (
                isinstance(func, ast.Attribute) and func.attr == "open"
            )
            if is_open:
                mode_args = [a for a in node.args[:2] if isinstance(a, ast.Constant)]
                mode_kwargs = [k.value for k in node.keywords if k.arg == "mode"]
                for arg in [*mode_args, *mode_kwargs]:
                    is_write = (
                        isinstance(arg, ast.Constant)
                        and isinstance(arg.value, str)
                        and bool(WRITE_MODE_CHARS & set(arg.value))
                    )
                    if is_write:
                        problems.append(f"open with write mode at line {node.lineno}")
    assert problems == []


def test_checker_detects_violations() -> None:
    """The tripwire must actually trip."""
    bad = ast.parse(
        "import socket\nfrom pathlib import Path\nPath('x').write_text('y')\nopen('f', 'w')"
    )
    assert "socket" in _imports(bad)
    attributes = {n.attr for n in ast.walk(bad) if isinstance(n, ast.Attribute)}
    assert attributes & FORBIDDEN_ATTRIBUTES == {"write_text"}
