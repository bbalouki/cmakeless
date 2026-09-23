"""C++20 module interfaces through the public API: modules= and add_module_sources()."""

from __future__ import annotations

from pathlib import Path

import pytest

from cmakeless import ConfigurationError, Project


@pytest.fixture
def modules_project(project_dir: Path) -> Project:
    """A project on disk with two C++20 module interface units."""
    (project_dir / "src" / "geometry.cppm").write_text(
        "export module geometry;\n", encoding="utf-8"
    )
    (project_dir / "src" / "shapes.cppm").write_text("export module shapes;\n", encoding="utf-8")
    return Project("demo", root=project_dir, cpp_std=23)


def test_library_modules_freeze_into_the_model(modules_project: Project) -> None:
    """Library modules freeze into the model."""
    modules_project.add_library("engine", modules=["src/geometry.cppm"])
    model = modules_project.freeze()
    assert model.libraries[0].cxx_modules == (Path("src/geometry.cppm"),)
    assert model.libraries[0].sources == ()


def test_executable_modules_freeze_into_the_model(modules_project: Project) -> None:
    """Executable modules freeze into the model."""
    modules_project.add_executable("app", sources=["src/main.cpp"], modules=["src/geometry.cppm"])
    model = modules_project.freeze()
    assert model.executables[0].cxx_modules == (Path("src/geometry.cppm"),)


def test_add_module_sources_appends(modules_project: Project) -> None:
    """Add module sources appends."""
    engine = modules_project.add_library("engine", modules=["src/geometry.cppm"])
    engine.add_module_sources("src/shapes.cppm")
    model = modules_project.freeze()
    assert model.libraries[0].cxx_modules == (Path("src/geometry.cppm"), Path("src/shapes.cppm"))


def test_module_globs_expand_and_sort(modules_project: Project) -> None:
    """Module globs expand and sort."""
    modules_project.add_library("engine", modules=["src/*.cppm"])
    model = modules_project.freeze()
    assert model.libraries[0].cxx_modules == (Path("src/geometry.cppm"), Path("src/shapes.cppm"))


def test_module_glob_matching_nothing_is_rejected(modules_project: Project) -> None:
    """Module glob matching nothing is rejected."""
    modules_project.add_library("engine", modules=["src/*.ixx"])
    with pytest.raises(ConfigurationError, match="Module pattern"):
        modules_project.freeze()


def test_missing_module_file_is_rejected(modules_project: Project) -> None:
    """Missing module file is rejected."""
    modules_project.add_library("engine", modules=["src/nope.cppm"])
    with pytest.raises(ConfigurationError, match="Module interface"):
        modules_project.freeze()


def test_a_module_only_library_needs_no_sources(modules_project: Project) -> None:
    """A module only library needs no sources."""
    modules_project.add_library("engine", modules=["src/geometry.cppm"])
    assert modules_project.freeze().libraries[0].name == "engine"


def test_modules_below_cpp20_are_rejected(project_dir: Path) -> None:
    """Modules below cpp20 are rejected."""
    (project_dir / "src" / "geometry.cppm").write_text(
        "export module geometry;\n", encoding="utf-8"
    )
    project = Project("demo", root=project_dir, cpp_std=17)
    project.add_library("engine", modules=["src/geometry.cppm"])
    with pytest.raises(ConfigurationError, match="Modules need C\\+\\+20 or later"):
        project.freeze()


def test_a_target_override_can_lift_the_project_below_cpp20(project_dir: Path) -> None:
    """A target override can lift the project below cpp20."""
    (project_dir / "src" / "geometry.cppm").write_text(
        "export module geometry;\n", encoding="utf-8"
    )
    project = Project("demo", root=project_dir, cpp_std=17)
    engine = project.add_library("engine", modules=["src/geometry.cppm"])
    engine.cpp_std = 20
    assert project.freeze().libraries[0].cpp_std == 20


def test_header_only_library_cannot_declare_modules(modules_project: Project) -> None:
    """Header only library cannot declare modules."""
    (modules_project.root / "include").mkdir()
    modules_project.add_library(
        "engine", kind="header_only", public_headers="include/", modules=["src/geometry.cppm"]
    )
    with pytest.raises(ConfigurationError, match="cannot declare C\\+\\+20 module interfaces"):
        modules_project.freeze()


def test_a_file_cannot_be_both_a_source_and_a_module(modules_project: Project) -> None:
    """A file cannot be both a source and a module."""
    modules_project.add_library(
        "engine", sources=["src/geometry.cppm"], modules=["src/geometry.cppm"]
    )
    with pytest.raises(ConfigurationError, match="both"):
        modules_project.freeze()


def test_installing_a_module_target_is_refused(modules_project: Project) -> None:
    """Installing a module target is refused."""
    engine = modules_project.add_library("engine", modules=["src/geometry.cppm"])
    modules_project.install(engine)
    with pytest.raises(ConfigurationError, match="still experimental"):
        modules_project.freeze()


def test_a_project_without_modules_is_unchanged(project_dir: Path) -> None:
    """A project without modules is unchanged."""
    project = Project("demo", root=project_dir, cpp_std=23)
    project.add_executable("app", sources=["src/main.cpp"])
    assert project.freeze().executables[0].cxx_modules == ()
