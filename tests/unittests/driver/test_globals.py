# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Global-variable probing against the real CMake engine."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from cmakeless.driver.globals import probe_globals
from cmakeless.errors import CMakeError
from cmakeless.model.nodes import ToolchainModel

requires_cmake = pytest.mark.skipif(shutil.which("cmake") is None, reason="cmake is not on PATH")


@requires_cmake
def test_probe_globals_discovers_host_platform_and_compiler(tmp_path: Path) -> None:
    """The host probe discovers real compiler and platform variables."""
    values = probe_globals("cmake", work_dir=tmp_path / "work", cpp_std=20, toolchain=None)
    assert values.get("CMAKE_CXX_COMPILER_ID")
    assert "WIN32" in values or "UNIX" in values


@requires_cmake
def test_probe_globals_omits_a_variable_cmake_never_defines(tmp_path: Path) -> None:
    """A variable CMake never defines on this host is simply absent.

    This is what lets CMakeGlobals map hasattr() to if(DEFINED ...) for
    free: an unset variable is missing from the dict, not present as "".
    """
    values = probe_globals("cmake", work_dir=tmp_path / "work", cpp_std=20, toolchain=None)
    assert "CMAKELESS_DOES_NOT_EXIST" not in values


@requires_cmake
def test_probe_globals_never_leaks_its_own_bookkeeping_variable(tmp_path: Path) -> None:
    """The probe's own dump-loop variable never masquerades as a real one."""
    values = probe_globals("cmake", work_dir=tmp_path / "work", cpp_std=20, toolchain=None)
    assert "_cmakeless_globals_all" not in values


@requires_cmake
def test_probe_globals_reflects_a_toolchain_seeded_variable(tmp_path: Path) -> None:
    """A toolchain's own seeded cache variable is visible in the probe.

    Confirms the generated toolchain file (the same emit_toolchain() the
    real build uses) is actually applied via CMAKE_TOOLCHAIN_FILE, not
    silently ignored.
    """
    toolchain = ToolchainModel(name="probe-test", variables=(("CMAKELESS_PROBE_MARKER", "hello"),))
    values = probe_globals("cmake", work_dir=tmp_path / "work", cpp_std=20, toolchain=toolchain)
    assert values.get("CMAKELESS_PROBE_MARKER") == "hello"


@requires_cmake
def test_probe_globals_raises_when_the_toolchain_is_broken(tmp_path: Path) -> None:
    """An unusable generated toolchain surfaces as a CMakeError, not a crash."""
    toolchain = ToolchainModel(
        name="broken",
        compiler="this-compiler-does-not-exist-anywhere",
        system_name="Generic",
        system_processor="testproc",
    )
    with pytest.raises(CMakeError, match="global variables"):
        probe_globals("cmake", work_dir=tmp_path / "work", cpp_std=20, toolchain=toolchain)
