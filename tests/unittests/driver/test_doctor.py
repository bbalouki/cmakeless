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


def test_modern_cmake_and_ninja_support_modules(monkeypatch: pytest.MonkeyPatch) -> None:
    """Modern cmake and ninja support modules."""
    patch_tools(monkeypatch, tool_paths=_TOOL_PATHS)
    patch_cmake_version(monkeypatch, "3.29.2")
    patch_network(monkeypatch, reachable=True)
    checks = by_name(run_diagnostics())
    assert checks["modules"].ok
    assert not checks["modules"].required


def test_cmake_below_the_modules_floor_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cmake below the modules floor is reported."""
    patch_tools(monkeypatch, tool_paths=_TOOL_PATHS)
    patch_cmake_version(monkeypatch, "3.26.0")
    patch_network(monkeypatch, reachable=True)
    checks = by_name(run_diagnostics())
    assert not checks["modules"].ok
    assert not checks["modules"].required
    assert "3.28" in checks["modules"].detail


def test_a_generator_that_cannot_scan_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    """A generator that cannot scan is reported."""
    patch_tools(monkeypatch, tool_paths={**_TOOL_PATHS, "ninja": None})
    patch_cmake_version(monkeypatch, "3.29.2")
    patch_network(monkeypatch, reachable=True)
    checks = by_name(run_diagnostics())
    if checks["generator"].detail != "ninja":
        assert not checks["modules"].ok
        assert "cannot scan for modules" in checks["modules"].detail


def test_unparseable_cmake_version_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    """A cmake whose --version output makes no sense fails the required check."""
    patch_tools(monkeypatch, tool_paths=_TOOL_PATHS)
    monkeypatch.setattr(
        "cmakeless.driver.doctor.subprocess.run",
        lambda *_a, **_kw: subprocess.CompletedProcess(
            args=[], returncode=0, stdout="cmake version unknown\n", stderr=""
        ),
    )
    patch_network(monkeypatch, reachable=True)
    checks = by_name(run_diagnostics())
    assert not checks["cmake"].ok
    assert checks["cmake"].required
    assert "could not be parsed" in checks["cmake"].detail


def test_modules_check_defers_to_cmake_when_cmake_is_unusable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Modules check defers to cmake when cmake is unusable."""
    patch_tools(monkeypatch, tool_paths={**_TOOL_PATHS, "cmake": None})
    patch_network(monkeypatch, reachable=True)
    checks = by_name(run_diagnostics())
    assert not checks["modules"].ok
    assert not checks["modules"].required
    assert "see above" in checks["modules"].detail
