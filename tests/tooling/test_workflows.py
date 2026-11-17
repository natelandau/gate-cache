"""Tests that CI runs each suite for the same files as its local gate, and a release runs all."""

from __future__ import annotations

from typing import Any

import pytest
import yaml

from tests.conftest import ROOT
from tests.tooling import load_duties

WORKFLOWS = ROOT / ".github" / "workflows"
CALLED = {
    "test-core": "tests-core.yml",
    "test-server": "tests-server.yml",
    "test-frontend": "tests-frontend.yml",
    "test-tooling": "tests-tooling.yml",
    "lint": "lint.yml",
}
SUITES = tuple(load_duties().SUITES)


def _load(name: str) -> dict[Any, Any]:
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def _triggers(doc: dict[Any, Any]) -> dict[str, Any]:
    # YAML 1.1 reads the bare key `on` as the boolean true
    return doc[True]


def _glob(pathspec: str) -> str:
    """Translate a git pathspec from duties.py to the GitHub `paths:` glob that matches it."""
    exclude = ":(exclude)"
    if pathspec.startswith(exclude):
        return "!" + _glob(pathspec.removeprefix(exclude))
    return f"{pathspec}**" if pathspec.endswith("/") else pathspec


@pytest.mark.parametrize("suite", SUITES)
def test_workflow_paths_match_suites(suite: str) -> None:
    """Each suite workflow triggers on exactly its gate's paths, in order, so excludes apply."""
    expected = [_glob(pathspec) for pathspec in load_duties().SUITES[suite]]
    triggers = _triggers(_load(f"tests-{suite}.yml"))
    assert triggers["push"]["paths"] == expected
    assert triggers["pull_request"]["paths"] == expected


@pytest.mark.parametrize("name", CALLED.values())
def test_suite_workflows_are_callable(name: str) -> None:
    """The release calls each workflow, and each can be run by hand."""
    triggers = _triggers(_load(name))
    assert "workflow_call" in triggers
    assert "workflow_dispatch" in triggers


def test_release_runs_everything() -> None:
    """A release calls every suite and lint with no condition, and publishes only after all."""
    jobs = _load("create-release.yml")["jobs"]
    for job_id, name in CALLED.items():
        assert jobs[job_id]["uses"] == f"./.github/workflows/{name}"
        assert "if" not in jobs[job_id]
    assert set(jobs["autorelease"]["needs"]) == set(CALLED)


@pytest.mark.parametrize("name", CALLED.values())
def test_release_never_skips(name: str) -> None:
    """The release commit's own skip condition never applies to a tag."""
    for job in _load(name)["jobs"].values():
        # A job with no condition never skips, which is also safe
        condition = job.get("if", "${{ github.ref_type == 'tag' ||")
        assert condition.startswith("${{ github.ref_type == 'tag' ||")


@pytest.mark.parametrize("job_id", CALLED)
def test_concurrency_names_the_workflow(job_id: str) -> None:
    """Under workflow_call the caller's name fills github.workflow, so groups need their own."""
    group = _load(CALLED[job_id])["concurrency"]["group"]
    assert group.startswith(CALLED[job_id].removesuffix(".yml") + "-")


def test_lint_validates_the_hook_manifest() -> None:
    """Lint runs on every change, so the manifest check cannot skip when the manifest changes."""
    steps = _load("lint.yml")["jobs"]["lint-project"]["steps"]
    assert any(
        "prek validate-manifest .pre-commit-hooks.yaml" in step.get("run", "") for step in steps
    )


def test_codecov_carries_forward_only_suite_flags() -> None:
    """A skipped suite keeps its last report, and no retired flag is carried forward."""
    config = yaml.safe_load((ROOT / "codecov.yml").read_text(encoding="utf-8"))["flag_management"]
    assert config["default_rules"]["carryforward"] is False
    flags = {flag["name"]: flag["carryforward"] for flag in config["individual_flags"]}
    assert flags == {"core": True, "server": True}
