"""Freeze-time validation catches mistakes before CMake ever runs."""

from __future__ import annotations

from pathlib import Path

import pytest

from cmakeless.errors import ConfigurationError
from cmakeless.model.nodes import ExecutableModel, ProjectModel
from cmakeless.model.validate import validate_project


def make_model(
    root: Path,
    *,
    name: str = "demo",
    cpp_std: int = 20,
    executables: tuple[ExecutableModel, ...] = (),
) -> ProjectModel:
    return ProjectModel(
        name=name,
        version="1.0.0",
        cpp_std=cpp_std,
        root_dir=root,
        source_script="build.py",
        executables=executables,
    )


def test_valid_project_passes(project_dir: Path) -> None:
    model = make_model(
        project_dir,
        executables=(ExecutableModel(name="app", sources=(Path("src/main.cpp"),)),),
    )
    validate_project(model)


def test_missing_source_reports_what_where_and_what_next(project_dir: Path) -> None:
    model = make_model(
        project_dir,
        executables=(ExecutableModel(name="app", sources=(Path("src/nope.cpp"),)),),
    )
    with pytest.raises(ConfigurationError) as excinfo:
        validate_project(model)
    message = str(excinfo.value)
    assert "src/nope.cpp" in message
    assert "app" in message
    assert "build.py" in message
    assert "typo" in message


def test_empty_sources_rejected(project_dir: Path) -> None:
    model = make_model(project_dir, executables=(ExecutableModel(name="app", sources=()),))
    with pytest.raises(ConfigurationError, match="no source files"):
        validate_project(model)


def test_duplicate_target_names_rejected(project_dir: Path) -> None:
    target = ExecutableModel(name="app", sources=(Path("src/main.cpp"),))
    model = make_model(project_dir, executables=(target, target))
    with pytest.raises(ConfigurationError, match="Duplicate target name"):
        validate_project(model)


@pytest.mark.parametrize("bad_name", ["my app", "app;rm", "", "1app$"])
def test_invalid_project_names_rejected(project_dir: Path, bad_name: str) -> None:
    model = make_model(project_dir, name=bad_name)
    with pytest.raises(ConfigurationError, match="Invalid project name"):
        validate_project(model)


@pytest.mark.parametrize("bad_std", [12, 15, 99, 0])
def test_unknown_cpp_std_rejected(project_dir: Path, bad_std: int) -> None:
    model = make_model(project_dir, cpp_std=bad_std)
    with pytest.raises(ConfigurationError, match="Unknown C\\+\\+ standard"):
        validate_project(model)
