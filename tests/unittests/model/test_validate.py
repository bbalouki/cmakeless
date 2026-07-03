"""Freeze-time validation catches mistakes before CMake ever runs."""

from __future__ import annotations

from pathlib import Path

import pytest

from cmakeless.errors import ConfigurationError
from cmakeless.model.nodes import (
    DependencyModel,
    ExecutableModel,
    LinkModel,
    ProjectModel,
    PythonModuleModel,
    SubprojectModel,
)
from cmakeless.model.validate import validate_project


def make_model(
    root: Path,
    *,
    name: str = "demo",
    cpp_std: int = 20,
    package_manager: str = "auto",
    source_script: str = "build.py",
    executables: tuple[ExecutableModel, ...] = (),
    dependencies: tuple[DependencyModel, ...] = (),
    subprojects: tuple[SubprojectModel, ...] = (),
    python_modules: tuple[PythonModuleModel, ...] = (),
) -> ProjectModel:
    """Build a frozen project rooted at the given directory."""
    return ProjectModel(
        name=name,
        version="1.0.0",
        cpp_std=cpp_std,
        root_dir=root,
        source_script=source_script,
        package_manager=package_manager,
        executables=executables,
        dependencies=dependencies,
        subprojects=subprojects,
        python_modules=python_modules,
    )


def fmt_dependency(*, version: str = "10.2.1") -> DependencyModel:
    """A metadata-complete fmt dependency."""
    return DependencyModel(
        name="fmt", version=version, cmake_name="fmt", link_targets=("fmt::fmt",)
    )


def test_valid_project_passes(project_dir: Path) -> None:
    """Valid project passes."""
    model = make_model(
        project_dir,
        executables=(ExecutableModel(name="app", sources=(Path("src/main.cpp"),)),),
    )
    validate_project(model)


def test_missing_source_reports_what_where_and_what_next(project_dir: Path) -> None:
    """Missing source reports what where and what next."""
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
    """Empty sources rejected."""
    model = make_model(project_dir, executables=(ExecutableModel(name="app", sources=()),))
    with pytest.raises(ConfigurationError, match="no source files"):
        validate_project(model)


def test_duplicate_target_names_rejected(project_dir: Path) -> None:
    """Duplicate target names rejected."""
    target = ExecutableModel(name="app", sources=(Path("src/main.cpp"),))
    model = make_model(project_dir, executables=(target, target))
    with pytest.raises(ConfigurationError, match="Duplicate target name"):
        validate_project(model)


@pytest.mark.parametrize("bad_name", ["my app", "app;rm", "", "1app$"])
def test_invalid_project_names_rejected(project_dir: Path, bad_name: str) -> None:
    """Invalid project names rejected."""
    model = make_model(project_dir, name=bad_name)
    with pytest.raises(ConfigurationError, match="Invalid project name"):
        validate_project(model)


@pytest.mark.parametrize("bad_std", [12, 15, 99, 0])
def test_unknown_cpp_std_rejected(project_dir: Path, bad_std: int) -> None:
    """Unknown cpp std rejected."""
    model = make_model(project_dir, cpp_std=bad_std)
    with pytest.raises(ConfigurationError, match="Unknown C\\+\\+ standard"):
        validate_project(model)


def test_unknown_package_manager_rejected(project_dir: Path) -> None:
    """Unknown package manager rejected."""
    model = make_model(project_dir, package_manager="npm")
    with pytest.raises(ConfigurationError, match="Unknown package manager"):
        validate_project(model)


def test_dependency_without_imported_targets_rejected(project_dir: Path) -> None:
    """Dependency without imported targets rejected."""
    incomplete = DependencyModel(name="fmt", version="10.2.1", cmake_name="fmt")
    model = make_model(project_dir, dependencies=(incomplete,))
    with pytest.raises(ConfigurationError, match="no imported targets"):
        validate_project(model)


def test_dependency_without_version_rejected(project_dir: Path) -> None:
    """Dependency without version rejected."""
    incomplete = DependencyModel(
        name="fmt", version="", cmake_name="fmt", link_targets=("fmt::fmt",)
    )
    model = make_model(project_dir, dependencies=(incomplete,))
    with pytest.raises(ConfigurationError, match="no version"):
        validate_project(model)


def test_external_link_must_match_a_dependency(project_dir: Path) -> None:
    """External link must match a dependency."""
    app = ExecutableModel(
        name="app",
        sources=(Path("src/main.cpp"),),
        links=(LinkModel(target="fmt::fmt", external=True),),
    )
    model = make_model(project_dir, executables=(app,))
    with pytest.raises(ConfigurationError, match="no dependency of this project"):
        validate_project(model)


def test_external_link_backed_by_a_dependency_passes(project_dir: Path) -> None:
    """External link backed by a dependency passes."""
    app = ExecutableModel(
        name="app",
        sources=(Path("src/main.cpp"),),
        links=(LinkModel(target="fmt::fmt", external=True),),
    )
    model = make_model(project_dir, executables=(app,), dependencies=(fmt_dependency(),))
    validate_project(model)


def test_subproject_package_manager_must_match_the_parent(project_dir: Path) -> None:
    """Subproject package manager must match the parent."""
    child = make_model(project_dir, name="child", package_manager="conan")
    parent = make_model(
        project_dir,
        package_manager="vcpkg",
        subprojects=(SubprojectModel(directory=Path("tools/child"), project=child),),
    )
    with pytest.raises(ConfigurationError, match="same package_manager"):
        validate_project(parent)


def test_conflicting_versions_across_the_tree_rejected(project_dir: Path) -> None:
    """Conflicting versions across the tree rejected."""
    child = make_model(
        project_dir,
        name="child",
        source_script="tools/child/build.py",
        dependencies=(fmt_dependency(version="11.0.0"),),
    )
    parent = make_model(
        project_dir,
        dependencies=(fmt_dependency(),),
        subprojects=(SubprojectModel(directory=Path("tools/child"), project=child),),
    )
    with pytest.raises(ConfigurationError) as excinfo:
        validate_project(parent)
    message = str(excinfo.value)
    assert "Conflicting versions" in message
    assert "10.2.1" in message
    assert "11.0.0" in message


def test_valid_python_module_passes(project_dir: Path) -> None:
    """Valid python module passes."""
    module = PythonModuleModel(name="core", sources=(Path("src/main.cpp"),), binding="pybind11")
    validate_project(make_model(project_dir, python_modules=(module,)))


def test_unknown_binding_backend_rejected(project_dir: Path) -> None:
    """Unknown binding backend rejected."""
    module = PythonModuleModel(name="core", sources=(Path("src/main.cpp"),), binding="cython")
    with pytest.raises(ConfigurationError) as excinfo:
        validate_project(make_model(project_dir, python_modules=(module,)))
    message = str(excinfo.value)
    assert "cython" in message
    assert "core" in message
    assert "build.py" in message


def test_python_module_missing_source_rejected(project_dir: Path) -> None:
    """Python module missing source rejected."""
    module = PythonModuleModel(name="core", sources=(Path("src/nope.cpp"),))
    with pytest.raises(ConfigurationError, match=r"src/nope\.cpp"):
        validate_project(make_model(project_dir, python_modules=(module,)))
