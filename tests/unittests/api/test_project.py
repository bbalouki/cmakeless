"""The Project builder freezes into a validated model."""

from __future__ import annotations

from pathlib import Path

import pytest

from cmakeless import ConfigurationError, Executable, Project


def test_add_executable_returns_builder(project_dir: Path) -> None:
    """Add executable returns builder."""
    project = Project("demo", root=project_dir)
    app = project.add_executable("app", sources=["src/main.cpp"])
    assert isinstance(app, Executable)
    assert app.name == "app"


def test_freeze_produces_model_with_tuples(project_dir: Path) -> None:
    """Freeze produces model with tuples."""
    project = Project("demo", version="2.1.0", cpp_std=23, root=project_dir)
    project.add_executable("app", sources=["src/main.cpp"])
    model = project.freeze()
    assert model.name == "demo"
    assert model.version == "2.1.0"
    assert model.cpp_std == 23
    assert model.root_dir == project_dir
    assert model.executables[0].sources == (Path("src/main.cpp"),)


def test_freeze_validates_missing_sources(project_dir: Path) -> None:
    """Freeze validates missing sources."""
    project = Project("demo", root=project_dir)
    project.add_executable("app", sources=["src/missing.cpp"])
    with pytest.raises(ConfigurationError, match=r"missing\.cpp"):
        project.freeze()


def test_freeze_validates_cpp_std(project_dir: Path) -> None:
    """Freeze validates cpp std."""
    project = Project("demo", cpp_std=42, root=project_dir)
    project.add_executable("app", sources=["src/main.cpp"])
    with pytest.raises(ConfigurationError, match="42"):
        project.freeze()


def test_add_sources_appends(project_dir: Path) -> None:
    """Add sources appends."""
    (project_dir / "src" / "extra.cpp").write_text("", encoding="utf-8")
    project = Project("demo", root=project_dir)
    app = project.add_executable("app", sources=["src/main.cpp"])
    app.add_sources("src/extra.cpp")
    model = project.freeze()
    assert Path("src/extra.cpp") in model.executables[0].sources


def test_root_defaults_to_calling_script_directory(project_dir: Path) -> None:
    """Root defaults to calling script directory.

    This test file is the "calling script", so the default root must be its
    directory, not the process working directory.
    """
    project = Project("demo")
    assert project.root == Path(__file__).resolve().parent


def test_generate_writes_cmakelists_without_cmake(project_dir: Path) -> None:
    """Generate writes cmakelists without cmake."""
    project = Project("demo", root=project_dir)
    project.add_executable("app", sources=["src/main.cpp"])
    written = project.generate()
    assert written == [project_dir / "CMakeLists.txt"]
    assert "add_executable(app)" in written[0].read_text(encoding="utf-8")
