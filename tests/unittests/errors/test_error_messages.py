# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Golden-file coverage for the highest-value error messages.

A regression in diagnostic quality should fail CI the same way a regression
in emitted CMake already does (tests/unittests/emitter/golden/). This does
not duplicate the many scattered pytest.raises(..., match=...) assertions
elsewhere: it snapshots only the multi-line, dynamic-listing, or
diagnostic-embedding messages, one per error class, where wording drift is
most likely and most damaging.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from cmakeless.api.dependencies import Dependencies
from cmakeless.api.modules import CMakeModule, check_file_reference
from cmakeless.driver.cmake_driver import CMakeDriver, resolve_tool
from cmakeless.driver.generators import Generator, GeneratorFamily
from cmakeless.driver.reflection import ModuleReflection
from cmakeless.errors import CMakeError, ConfigurationError, DependencyError, ToolchainError
from cmakeless.model.nodes import ModuleKind

GOLDEN_DIR = Path(__file__).parent / "golden"


def _golden(name: str) -> str:
    """Read one golden fixture, trailing newline stripped."""
    return (GOLDEN_DIR / f"{name}.txt").read_text(encoding="utf-8").rstrip("\n")


def test_configuration_error_module_no_such_function() -> None:
    """CMakeModule.call() names the unknown function and lists what exists."""
    module = CMakeModule(
        kind=ModuleKind.FILE,
        reference="cmake/helper.cmake",
        module_path=None,
        reflection=ModuleReflection(functions=("known_fn",), variables=()),
        script="cmakelessfile.py",
    )
    with pytest.raises(ConfigurationError) as excinfo:
        module.call("unknown_fn")
    assert str(excinfo.value) == _golden("configuration_error_module_no_such_function")


def test_configuration_error_include_path_not_relative() -> None:
    """check_file_reference() rejects a path escaping the project root."""
    with pytest.raises(ConfigurationError) as excinfo:
        check_file_reference(
            Path("/etc/evil.cmake"), root=Path("/project"), script="cmakelessfile.py"
        )
    assert str(excinfo.value) == _golden("configuration_error_include_path_not_relative")


def test_dependency_error_missing_lockfile(project_dir: Path) -> None:
    """Dependencies.sbom() names the missing lockfile and the fix."""
    from cmakeless import Project

    project = Project("demo", root=project_dir)
    with pytest.raises(DependencyError) as excinfo:
        Dependencies(project).sbom()
    lock_path = project_dir / "cmakeless.lock"
    normalized = str(excinfo.value).replace(str(lock_path), "<LOCKFILE_PATH>")
    assert normalized == _golden("dependency_error_missing_lockfile")


def test_toolchain_error_cmake_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """resolve_tool() explains that cmake is missing and how to get it."""
    monkeypatch.setattr("cmakeless.driver.cmake_driver.shutil.which", lambda _tool: None)
    with pytest.raises(ToolchainError) as excinfo:
        resolve_tool("cmake")
    assert str(excinfo.value) == _golden("toolchain_error_cmake_missing")


_FAKE_CMAKE_ERROR_STDOUT = (
    "-- Configuring done\n"
    "CMake Error at CMakeLists.txt:12 (add_executable):\n"
    "  Cannot find source file:\n"
    "\n"
    "    missing.cpp\n"
)


def _driver_with_failing_configure(
    monkeypatch: pytest.MonkeyPatch, *, source_dir: Path, build_dir: Path
) -> CMakeDriver:
    """Build a CMakeDriver whose configure() always fails with a canned error."""
    monkeypatch.setattr("cmakeless.driver.cmake_driver.resolve_tool", lambda _tool: "cmake")
    monkeypatch.setattr(
        "cmakeless.driver.cmake_driver.subprocess.run",
        lambda command, **_kw: subprocess.CompletedProcess(
            args=command, returncode=1, stdout=_FAKE_CMAKE_ERROR_STDOUT, stderr=""
        ),
    )
    return CMakeDriver(
        source_dir=source_dir,
        build_dir=build_dir,
        generator=Generator(name="ninja", cmake_args=("-G", "Ninja"), family=GeneratorFamily.NINJA),
        use_cache=False,
    )


def test_cmake_error_configure_failure_with_diagnostic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed configure surfaces the first parsed diagnostic and the log path."""
    source_dir = tmp_path
    build_dir = tmp_path / "build"
    driver = _driver_with_failing_configure(monkeypatch, source_dir=source_dir, build_dir=build_dir)
    with pytest.raises(CMakeError) as excinfo:
        driver.configure()
    log_path = build_dir / "cmakeless-log.txt"
    normalized = (
        str(excinfo.value)
        .replace(str(log_path), "<LOG_PATH>")
        .replace(str(build_dir), "<BUILD_DIR>")
        .replace(str(source_dir), "<SOURCE_DIR>")
    )
    assert normalized == _golden("cmake_error_configure_failure_with_diagnostic")
