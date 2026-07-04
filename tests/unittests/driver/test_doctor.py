# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""'cmakeless doctor' environment diagnostics, subprocess/network mocked."""

from __future__ import annotations

import subprocess
import urllib.error

import pytest

from cmakeless.driver.doctor import DoctorCheck, run_diagnostics

_TOOL_PATHS = {
    "cmake": "/usr/bin/cmake",
    "ccache": "/usr/bin/ccache",
    "sccache": None,
    "vcpkg": None,
    "conan": None,
    "ninja": "/usr/bin/ninja",
}


def patch_tools(monkeypatch: pytest.MonkeyPatch, *, tool_paths: dict[str, str | None]) -> None:
    """Make the given tools (and only those) discoverable on PATH."""
    monkeypatch.setattr("cmakeless.driver.doctor.shutil.which", lambda tool: tool_paths.get(tool))
    monkeypatch.setattr(
        "cmakeless.driver.generators.shutil.which", lambda tool: tool_paths.get(tool)
    )


def patch_cmake_version(monkeypatch: pytest.MonkeyPatch, version: str) -> None:
    """Make 'cmake --version' report the given version."""
    monkeypatch.setattr(
        "cmakeless.driver.doctor.subprocess.run",
        lambda *_a, **_kw: subprocess.CompletedProcess(
            args=[], returncode=0, stdout=f"cmake version {version}\n", stderr=""
        ),
    )


def patch_network(monkeypatch: pytest.MonkeyPatch, *, reachable: bool) -> None:
    """Make the network probe succeed or fail."""
    if reachable:
        monkeypatch.setattr(
            "cmakeless.driver.doctor.urllib.request.urlopen",
            lambda *_a, **_kw: _NullResponse(),
        )
    else:

        def fail(*_a: object, **_kw: object) -> object:
            """Simulate an unreachable network."""
            raise urllib.error.URLError("no route to host")

        monkeypatch.setattr("cmakeless.driver.doctor.urllib.request.urlopen", fail)


class _NullResponse:
    """A urlopen()-style context manager that does nothing."""

    def __enter__(self) -> _NullResponse:
        """Enter the context, returning self."""
        return self

    def __exit__(self, *exc_info: object) -> None:
        """Exit the context; nothing to clean up."""


def by_name(checks: tuple[DoctorCheck, ...]) -> dict[str, DoctorCheck]:
    """Index DoctorCheck results by name for easy assertions."""
    return {check.name: check for check in checks}


def test_everything_present_and_reachable_is_all_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    """Everything present and reachable is all ok."""
    patch_tools(monkeypatch, tool_paths=_TOOL_PATHS)
    patch_cmake_version(monkeypatch, "3.29.2")
    patch_network(monkeypatch, reachable=True)
    checks = by_name(run_diagnostics())
    assert checks["cmake"].ok
    assert checks["generator"].ok
    assert checks["generator"].detail == "ninja"
    assert checks["ccache"].ok
    assert checks["network"].ok
    assert not checks["sccache"].ok
    assert not checks["sccache"].required


def test_missing_cmake_is_required_and_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing cmake is required and fails."""
    patch_tools(monkeypatch, tool_paths={**_TOOL_PATHS, "cmake": None})
    patch_network(monkeypatch, reachable=True)
    checks = by_name(run_diagnostics())
    assert not checks["cmake"].ok
    assert checks["cmake"].required


def test_old_cmake_version_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Old cmake version is rejected."""
    patch_tools(monkeypatch, tool_paths=_TOOL_PATHS)
    patch_cmake_version(monkeypatch, "3.10.0")
    patch_network(monkeypatch, reachable=True)
    checks = by_name(run_diagnostics())
    assert not checks["cmake"].ok
    assert "older than" in checks["cmake"].detail


def test_unreachable_network_is_optional(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unreachable network is optional."""
    patch_tools(monkeypatch, tool_paths=_TOOL_PATHS)
    patch_cmake_version(monkeypatch, "3.29.2")
    patch_network(monkeypatch, reachable=False)
    checks = by_name(run_diagnostics())
    assert not checks["network"].ok
    assert not checks["network"].required
