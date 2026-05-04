# Copyright SUSE LLC
# SPDX-License-Identifier: MIT
"""Test increment approver diff."""

from __future__ import annotations

from typing import TYPE_CHECKING

from openqabot.loader.incrementconfig import IncrementConfig

from .helpers import prepare_approver

if TYPE_CHECKING:
    import pytest


def test_package_diff_repo(caplog: pytest.LogCaptureFixture) -> None:
    approver = prepare_approver(caplog)
    config = IncrementConfig(distri="sle", version="any", flavor="any", project_base="BASE", diff_project_suffix="DIFF")
    res = approver.get_package_diff(None, config)
    assert res == {}


def test_package_diff_none(caplog: pytest.LogCaptureFixture) -> None:
    approver = prepare_approver(caplog)
    config = IncrementConfig(distri="sle", version="any", flavor="any", diff_project_suffix="none")
    res = approver.get_package_diff(None, config)
    assert res == {}


def test_package_diff_cached(caplog: pytest.LogCaptureFixture) -> None:
    approver = prepare_approver(caplog)
    config = IncrementConfig(
        distri="sle",
        version="any",
        flavor="any",
        project_base="BASE",
        build_project_suffix="TEST",
        diff_project_suffix="DIFF",
    )
    res = approver.get_package_diff(None, config)
    assert res == {}


def test_package_diff_source_report_no_request(caplog: pytest.LogCaptureFixture) -> None:
    approver = prepare_approver(caplog)
    config = IncrementConfig(
        distri="sle", version="any", flavor="any", project_base="BASE", diff_project_suffix="source-report"
    )
    res = approver.get_package_diff(None, config)
    assert res == {}
    assert "Source report diff requested but no request found" in caplog.text


def test_package_diff_reference_repos(caplog: pytest.LogCaptureFixture) -> None:
    approver = prepare_approver(caplog)
    config = IncrementConfig(
        distri="sle",
        version="16.0",
        flavor="any",
        project_base="BASE",
        build_project_suffix="BUILD",
        diff_project_suffix="DIFF",
        flavor_suffix="Increments",
    )
    res = approver.get_package_diff(None, config)
    assert res == {}


def test_package_diff_skip_debug(caplog: pytest.LogCaptureFixture) -> None:
    approver = prepare_approver(caplog)
    config = IncrementConfig(
        distri="sle",
        version="any",
        flavor="any",
        project_base="BASE",
        build_project_suffix="BUILD",
        diff_project_suffix="DIFF-Debug",
    )
    res = approver.get_package_diff(None, config)
    assert res == {}
