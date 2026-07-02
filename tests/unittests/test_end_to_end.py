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
    executable_name = f"{name}.exe" if os.name == "nt" else name
    matches = [path for path in build_dir.rglob(executable_name) if path.is_file()]
    assert matches, f"no {executable_name} produced under {build_dir}"
    return matches[0]


@requires_cmake
def test_hello_world_builds_and_runs(tmp_path: Path) -> None:
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


@requires_cmake
def test_static_library_links_into_executable(tmp_path: Path) -> None:
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
