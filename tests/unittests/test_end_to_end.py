"""End-to-end: the whole pipeline against the real CMake engine.

Skipped when CMake is not on PATH; everything above the driver layer is
covered by the other tests without it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from cmakeless import CMakeError, Project

requires_cmake = pytest.mark.skipif(shutil.which("cmake") is None, reason="cmake is not on PATH")

HELLO_CPP = """\
#include <iostream>

auto main() -> int
{
    std::cout << "Hello from cmakeless!\\n";
    return 0;
}
"""


def find_binary(build_dir: Path, name: str) -> Path:
    """Locate a produced executable anywhere under the build tree."""
    executable_name = f"{name}.exe" if os.name == "nt" else name
    matches = [path for path in build_dir.rglob(executable_name) if path.is_file()]
    assert matches, f"no {executable_name} produced under {build_dir}"
    return matches[0]


@requires_cmake
def test_hello_world_builds_and_runs(tmp_path: Path) -> None:
    """Hello world builds and runs."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.cpp").write_text(HELLO_CPP, encoding="utf-8")

    project = Project("hello", version="1.0.0", cpp_std=20, root=tmp_path)
    project.add_executable("hello", sources=["src/main.cpp"])
    project.build()

    binary = find_binary(tmp_path / "build", "hello")
    result = subprocess.run([str(binary)], capture_output=True, text=True, check=True)
    assert "Hello from cmakeless!" in result.stdout


GREETER_HPP = """\
#pragma once
#include <string>

[[nodiscard]] auto greeting() -> std::string;
"""

GREETER_CPP = """\
#include "greeter.hpp"

auto greeting() -> std::string
{
    return "Hello from the engine library!";
}
"""

LIB_MAIN_CPP = """\
#include <iostream>
#include "greeter.hpp"

auto main() -> int
{
    std::cout << greeting() << "\\n";
    return 0;
}
"""


PASSING_TEST_CPP = """\
#include "greeter.hpp"

auto main() -> int
{
    return greeting() == "Hello from the engine library!" ? 0 : 1;
}
"""

FAILING_TEST_CPP = """\
auto main() -> int
{
    return 1;
}
"""


def write_library_sources(tmp_path: Path) -> None:
    """Put the greeter library's sources and headers on disk."""
    (tmp_path / "src").mkdir()
    (tmp_path / "include").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "include" / "greeter.hpp").write_text(GREETER_HPP, encoding="utf-8")
    (tmp_path / "src" / "greeter.cpp").write_text(GREETER_CPP, encoding="utf-8")


def library_project(tmp_path: Path) -> Project:
    """A library project with sources on disk, ready for tests or install."""
    write_library_sources(tmp_path)
    project = Project("libdemo", version="0.1.0", cpp_std=20, root=tmp_path)
    project.add_library("engine", sources=["src/greeter.cpp"], public_headers="include/")
    return project


@requires_cmake
def test_plain_test_target_runs_through_ctest(tmp_path: Path) -> None:
    """Plain test target runs through ctest."""
    project = library_project(tmp_path)
    (tmp_path / "tests" / "engine_test.cpp").write_text(PASSING_TEST_CPP, encoding="utf-8")
    tests = project.add_test("engine_tests", sources=["tests/engine_test.cpp"], framework="none")
    tests.link(project._libraries[0])
    project.test()
    log = (tmp_path / "build" / "cmakeless-log.txt").read_text(encoding="utf-8")
    assert "100% tests passed" in log


@requires_cmake
def test_failing_test_raises_a_structured_error(tmp_path: Path) -> None:
    """Failing test raises a structured error."""
    project = library_project(tmp_path)
    (tmp_path / "tests" / "engine_test.cpp").write_text(FAILING_TEST_CPP, encoding="utf-8")
    project.add_test("engine_tests", sources=["tests/engine_test.cpp"], framework="none")
    with pytest.raises(CMakeError, match="test failed"):
        project.test()


@requires_cmake
def test_install_ships_headers_and_config_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Install ships headers and config files."""
    from cmakeless.cli import main

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    write_library_sources(project_dir)
    build_py = (
        "from cmakeless import Project\n"
        'project = Project("libdemo", version="0.1.0", cpp_std=20)\n'
        'engine = project.add_library("engine", sources=["src/greeter.cpp"],'
        ' public_headers="include/")\n'
        "project.install(engine, headers=True)\n"
        "project.build()\n"
    )
    (project_dir / "build.py").write_text(build_py, encoding="utf-8")
    prefix = tmp_path / "prefix"
    monkeypatch.chdir(project_dir)
    assert main(["install", "--prefix", str(prefix)]) == 0
    assert (prefix / "include" / "greeter.hpp").is_file()
    assert (prefix / "lib" / "cmake" / "libdemo" / "libdemoConfig.cmake").is_file()
    assert (prefix / "lib" / "cmake" / "libdemo" / "libdemoTargets.cmake").is_file()


@requires_cmake
def test_preset_build_uses_its_own_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Preset build uses its own tree."""
    from cmakeless.cli import main

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.cpp").write_text(HELLO_CPP, encoding="utf-8")
    build_py = (
        "from cmakeless import Preset, Project\n"
        'project = Project("hello", cpp_std=20)\n'
        'project.add_executable("hello", sources=["src/main.cpp"])\n'
        'project.add_preset(Preset("release", optimize="release"))\n'
        "project.build()\n"
    )
    (tmp_path / "build.py").write_text(build_py, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert main(["build", "--preset", "release"]) == 0
    cache = (tmp_path / "build" / "release" / "CMakeCache.txt").read_text(encoding="utf-8")
    assert "CMAKE_BUILD_TYPE:STRING=Release" in cache
    binary = find_binary(tmp_path / "build" / "release", "hello")
    result = subprocess.run([str(binary)], capture_output=True, text=True, check=True)
    assert "Hello from cmakeless!" in result.stdout


@requires_cmake
def test_package_produces_a_zip_archive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Package produces a zip archive."""
    from cmakeless.cli import main

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.cpp").write_text(HELLO_CPP, encoding="utf-8")
    build_py = (
        "from cmakeless import Project\n"
        'project = Project("hello", version="1.0.0", cpp_std=20)\n'
        'app = project.add_executable("hello", sources=["src/main.cpp"])\n'
        "project.install(app)\n"
        'project.package(formats=["zip"])\n'
        "project.build()\n"
    )
    (tmp_path / "build.py").write_text(build_py, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert main(["package"]) == 0
    archives = list((tmp_path / "build").glob("hello-1.0.0-*.zip"))
    assert archives, "cpack produced no zip archive"


@requires_cmake
def test_configure_publishes_compile_commands(tmp_path: Path) -> None:
    """Configure publishes compile commands."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.cpp").write_text(HELLO_CPP, encoding="utf-8")
    project = Project("hello", cpp_std=20, root=tmp_path)
    project.add_executable("hello", sources=["src/main.cpp"])
    project.configure()
    # Multi-config generators legitimately produce none; Ninja always does.
    if (tmp_path / "build" / "compile_commands.json").is_file():
        assert (tmp_path / "compile_commands.json").is_file()


@requires_cmake
def test_static_library_links_into_executable(tmp_path: Path) -> None:
    """Static library links into executable."""
    (tmp_path / "src").mkdir()
    (tmp_path / "include").mkdir()
    (tmp_path / "include" / "greeter.hpp").write_text(GREETER_HPP, encoding="utf-8")
    (tmp_path / "src" / "greeter.cpp").write_text(GREETER_CPP, encoding="utf-8")
    (tmp_path / "src" / "main.cpp").write_text(LIB_MAIN_CPP, encoding="utf-8")

    project = Project("libdemo", version="0.1.0", cpp_std=20, warnings="strict", root=tmp_path)
    engine = project.add_library("engine", sources=["src/greeter.cpp"], public_headers="include/")
    app = project.add_executable("app", sources=["src/main.cpp"])
    app.link(engine)
    project.build()

    binary = find_binary(tmp_path / "build", "app")
    result = subprocess.run([str(binary)], capture_output=True, text=True, check=True)
    assert "Hello from the engine library!" in result.stdout


@requires_cmake
def test_compile_failure_becomes_structured_cmake_error(tmp_path: Path) -> None:
    """Compile failure becomes structured cmake error."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.cpp").write_text(
        "auto main() -> int { return undeclared_thing; }\n", encoding="utf-8"
    )
    project = Project("broken", cpp_std=20, root=tmp_path)
    project.add_executable("broken", sources=["src/main.cpp"])
    with pytest.raises(CMakeError) as excinfo:
        project.build()
    error = excinfo.value
    assert error.exit_code != 0
    assert error.log_path is not None and error.log_path.is_file()
    assert error.diagnostics, "compiler output should yield at least one diagnostic"
    assert any("undeclared_thing" in diag.message for diag in error.diagnostics)
