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

from cmakeless import Project

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
