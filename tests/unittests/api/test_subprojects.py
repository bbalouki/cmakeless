"""Subprojects: Composite structure with isolated scopes and description mode."""

from __future__ import annotations

from pathlib import Path

import pytest

from cmakeless import ConfigurationError, Project

CHILD_BUILD_PY = """\
from cmakeless import Project

project = Project("tool", version="0.1.0", cpp_std=20)
project.add_executable("tool", sources=["main.cpp"])
project.build()
"""


def write_child(parent_dir: Path, directory: str, build_py: str = CHILD_BUILD_PY) -> Path:
    """Write a child project (cmakelessfile.py plus main.cpp) under the parent dir."""
    child_dir = parent_dir / directory
    child_dir.mkdir(parents=True)
    (child_dir / "cmakelessfile.py").write_text(build_py, encoding="utf-8")
    (child_dir / "main.cpp").write_text("auto main() -> int { return 0; }\n", encoding="utf-8")
    return child_dir


def test_add_subproject_captures_child_without_building(project_dir: Path) -> None:
    """Add subproject captures child without building."""
    write_child(project_dir, "tools/stamp")
    parent = Project("demo", root=project_dir)
    parent.add_executable("app", sources=["src/main.cpp"])
    child = parent.add_subproject("tools/stamp")
    # The child's cmakelessfile.py called project.build(), but description mode made
    # it a no-op: no CMakeLists.txt and no build directory may exist yet.
    assert child.name == "tool"
    assert not (project_dir / "tools" / "stamp" / "build").exists()
    assert not (project_dir / "tools" / "stamp" / "CMakeLists.txt").exists()

    model = parent.freeze()
    assert model.subprojects[0].directory == Path("tools/stamp")
    assert model.subprojects[0].project.name == "tool"


def test_missing_child_build_py_is_reported(project_dir: Path) -> None:
    """Missing child build py is reported."""
    parent = Project("demo", root=project_dir)
    with pytest.raises(ConfigurationError, match="no build description"):
        parent.add_subproject("tools/ghost")


def test_child_with_two_projects_is_rejected(project_dir: Path) -> None:
    """Child with two projects is rejected."""
    two_projects = (
        "from cmakeless import Project\n"
        "first = Project('one', root='.')\n"
        "second = Project('two', root='.')\n"
    )
    write_child(project_dir, "tools/twins", two_projects)
    parent = Project("demo", root=project_dir)
    with pytest.raises(ConfigurationError, match="exactly one"):
        parent.add_subproject("tools/twins")


def test_duplicate_subproject_directory_rejected(project_dir: Path) -> None:
    """Duplicate subproject directory rejected."""
    write_child(project_dir, "tools/stamp")
    parent = Project("demo", root=project_dir)
    parent.add_executable("app", sources=["src/main.cpp"])
    parent.add_subproject("tools/stamp")
    parent.add_subproject("tools/stamp")
    with pytest.raises(ConfigurationError, match="added twice"):
        parent.freeze()


def test_subproject_cycle_guard(project_dir: Path) -> None:
    # The child tries to add its own parent directory as a subproject.
    """Subproject cycle guard."""
    recursive_child = (
        "from cmakeless import Project\n"
        "project = Project('tool')\n"
        "project.add_subproject('../..')\n"
    )
    write_child(project_dir, "tools/loop", recursive_child)
    (project_dir / "cmakelessfile.py").write_text(
        "from cmakeless import Project\n"
        "project = Project('demo')\n"
        "project.add_subproject('tools/loop')\n",
        encoding="utf-8",
    )
    parent = Project("demo", root=project_dir)
    with pytest.raises(ConfigurationError, match="cycle"):
        parent.add_subproject("tools/loop")


def test_child_sources_validated_against_child_root(project_dir: Path) -> None:
    """Child sources validated against child root."""
    child_dir = write_child(project_dir, "tools/stamp")
    (child_dir / "main.cpp").unlink()
    parent = Project("demo", root=project_dir)
    parent.add_executable("app", sources=["src/main.cpp"])
    parent.add_subproject("tools/stamp")
    with pytest.raises(ConfigurationError, match=r"main.cpp"):
        parent.freeze()


def test_generate_writes_one_cmakelists_per_project(project_dir: Path) -> None:
    """Generate writes one cmakelists per project."""
    write_child(project_dir, "tools/stamp")
    parent = Project("demo", root=project_dir)
    parent.add_executable("app", sources=["src/main.cpp"])
    parent.add_subproject("tools/stamp")
    written = parent.generate()
    assert written == [
        project_dir / "CMakeLists.txt",
        project_dir / "tools" / "stamp" / "CMakeLists.txt",
    ]
    parent_text = written[0].read_text(encoding="utf-8")
    child_text = written[1].read_text(encoding="utf-8")
    assert "add_subdirectory(tools/stamp)" in parent_text
    assert "project(tool" in child_text
    # Each generated file is standalone, so the subproject can also be built
    # on its own with plain CMake.
    assert "cmake_minimum_required" in child_text
