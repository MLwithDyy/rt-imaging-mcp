"""Release and community files that other tests and the release workflow rely on."""

from __future__ import annotations

import re
from pathlib import Path

import rt_imaging_mcp

REPO = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (REPO / relative).read_text(encoding="utf-8")


def test_version_is_a_valid_release_or_pre_release_number() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+(?:(?:a|b|rc)\d+|\.dev\d+)?", rt_imaging_mcp.__version__)


def test_version_has_a_single_source() -> None:
    pyproject = read("pyproject.toml")
    assert 'dynamic = ["version"]' in pyproject
    assert "[tool.hatch.version]" in pyproject
    assert not re.search(r"^version\s*=", pyproject, re.MULTILINE)


def test_changelog_has_an_unreleased_section_or_the_current_version() -> None:
    changelog = read("CHANGELOG.md")
    assert "## [Unreleased]" in changelog or f"## [{rt_imaging_mcp.__version__}]" in changelog


def test_community_and_policy_files_exist() -> None:
    for name in (
        "LICENSE",
        "NOTICE",
        "SECURITY.md",
        "CONTRIBUTING.md",
        "CHANGELOG.md",
        "docs/threat-model.md",
        "docs/validation.md",
        "docs/releasing.md",
        ".github/pull_request_template.md",
        ".github/ISSUE_TEMPLATE/bug_report.md",
        ".github/ISSUE_TEMPLATE/feature_request.md",
    ):
        assert (REPO / name).is_file(), name


def test_issue_templates_forbid_patient_data_and_blank_issues() -> None:
    assert "Do not paste patient data" in read(".github/ISSUE_TEMPLATE/bug_report.md")
    config = read(".github/ISSUE_TEMPLATE/config.yml")
    assert "blank_issues_enabled: false" in config
    assert "security/advisories/new" in config


def test_security_policy_asks_for_private_reporting_and_no_patient_data() -> None:
    policy = read("SECURITY.md")
    assert "Report a vulnerability" in policy
    assert "Never include real patient data" in policy


def test_release_workflow_checks_tag_tests_and_uses_trusted_publishing() -> None:
    workflow = read(".github/workflows/release.yml")
    assert "GITHUB_REF_NAME" in workflow
    assert "uv run pytest" in workflow
    assert "id-token: write" in workflow
    assert "environment: pypi" in workflow
    assert "PYPI_API_TOKEN" not in workflow and "password:" not in workflow


def test_testpypi_workflow_is_manual_only() -> None:
    workflow = read(".github/workflows/release-testpypi.yml")
    assert "workflow_dispatch" in workflow
    assert "push:" not in workflow
    assert "environment: testpypi" in workflow


def test_no_workflow_grants_write_permissions_by_default() -> None:
    for name in ("ci.yml", "release.yml", "release-testpypi.yml"):
        assert re.search(
            r"^permissions:\n  contents: read", read(f".github/workflows/{name}"), re.MULTILINE
        )


def test_keywords_do_not_advertise_unimplemented_features() -> None:
    keywords_line = next(
        line for line in read("pyproject.toml").splitlines() if line.startswith("keywords")
    )
    assert "radiomics" not in keywords_line
