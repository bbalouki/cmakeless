# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""End-to-end dependency resolution against the real CMake engine.

These tests download and compile a real third-party package, so they are
double-gated: CMake must be on PATH and CMAKELESS_NETWORK_TESTS=1 must be
set (CI sets it; offline development runs skip).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from cmakeless import Project

requires_cmake_and_network = pytest.mark.skipif(
    shutil.which("cmake") is None or os.environ.get("CMAKELESS_NETWORK_TESTS") != "1",
    reason="needs cmake on PATH and CMAKELESS_NETWORK_TESTS=1",
)

FMT_MAIN_CPP = """\
#include <fmt/core.h>

auto main() -> int
{
    fmt::print("Hello from {}!\\n", "fmt");
    return 0;
}
"""


def find_binary(build_dir: Path, name: str) -> Path:
    """Locate a produced executable anywhere under the build tree."""
    executable_name = f"{name}.exe" if os.name == "nt" else name
    matches = [path for path in build_dir.rglob(executable_name) if path.is_file()]
    assert matches, f"no {executable_name} produced under {build_dir}"
    return matches[0]


@requires_cmake_and_network
def test_fmt_dependency_builds_through_the_fallback(tmp_path: Path) -> None:
    """Fmt dependency builds through the fallback."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.cpp").write_text(FMT_MAIN_CPP, encoding="utf-8")

    project = Project("fmt_demo", version="1.0.0", cpp_std=20, root=tmp_path)
    app = project.add_executable("fmt_demo", sources=["src/main.cpp"])
    app.depends("fmt/10.2.1")
    project.build()

    binary = find_binary(tmp_path / "build", "fmt_demo")
    result = subprocess.run([str(binary)], capture_output=True, text=True, check=True)
    assert "Hello from fmt!" in result.stdout

    lock_path = tmp_path / "cmakeless.lock"
    assert lock_path.is_file()
    first_lock = lock_path.read_bytes()
    # A second generation resolves from the lockfile alone and is
    # byte-identical: the reproducibility half of the exit criterion.
    project.generate()
    assert lock_path.read_bytes() == first_lock


CATCH2_TEST_CPP = """\
#include <catch2/catch_test_macros.hpp>

TEST_CASE("arithmetic still works")
{
    REQUIRE(2 + 2 == 4);
}
"""


@requires_cmake_and_network
def test_catch2_tests_build_and_run_through_ctest(tmp_path: Path) -> None:
    """Catch2 tests build and run through ctest."""
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "smoke_test.cpp").write_text(CATCH2_TEST_CPP, encoding="utf-8")

    project = Project("catch_demo", version="1.0.0", cpp_std=20, root=tmp_path)
    project.add_test("smoke_tests", sources=["tests/smoke_test.cpp"], framework="catch2")
    project.test()

    log = (tmp_path / "build" / "cmakeless-log.txt").read_text(encoding="utf-8")
    assert "100% tests passed" in log
