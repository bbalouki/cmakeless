# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Library targets, the link graph, and compile settings through the public API."""

from __future__ import annotations

from pathlib import Path

import pytest

from cmakeless import ConfigurationError, Library, Project
from cmakeless.model.nodes import LibraryKind, WhenKind


@pytest.fixture
def library_project(project_dir: Path) -> Project:
    """A project on disk with sources, an include dir, and an extra engine.cpp."""
    (project_dir / "include").mkdir()
    (project_dir / "src" / "engine.cpp").write_text("", encoding="utf-8")
    return Project("demo", root=project_dir)


def test_add_library_returns_builder(library_project: Project) -> None:
    """Add library returns builder."""
    engine = library_project.add_library("engine", sources=["src/engine.cpp"])
    assert isinstance(engine, Library)
    assert engine.kind == "static"


@pytest.mark.parametrize("kind", ["static", "shared"])
def test_library_kinds_freeze(library_project: Project, kind: str) -> None:
    """Library kinds freeze."""
    library_project.add_library(
        "engine",
        sources=["src/engine.cpp"],
        public_headers="include/",
        kind=kind,  # type: ignore[arg-type]
    )
    model = library_project.freeze()
    assert model.libraries[0].kind is LibraryKind(kind)
    assert model.libraries[0].public_include_dirs == (Path("include"),)


def test_header_only_library(library_project: Project) -> None:
    """Header only library."""
    library_project.add_library("hdrs", public_headers="include/", kind="header_only")
    model = library_project.freeze()
    assert model.libraries[0].kind is LibraryKind.HEADER_ONLY
    assert model.libraries[0].sources == ()


def test_unknown_kind_rejected_immediately(library_project: Project) -> None:
    """Unknown kind rejected immediately."""
    with pytest.raises(ConfigurationError, match="Unknown library kind"):
        library_project.add_library("engine", sources=["src/engine.cpp"], kind="modular")  # type: ignore[arg-type]


def test_header_only_with_sources_rejected(library_project: Project) -> None:
    """Header only with sources rejected."""
    library_project.add_library("hdrs", sources=["src/engine.cpp"], kind="header_only")
    with pytest.raises(ConfigurationError, match="must not list source files"):
        library_project.freeze()


def test_missing_public_headers_dir_rejected(library_project: Project) -> None:
    """Missing public headers dir rejected."""
    library_project.add_library("engine", sources=["src/engine.cpp"], public_headers="headers/")
    with pytest.raises(ConfigurationError, match="does not exist"):
        library_project.freeze()


def test_link_records_visibility(library_project: Project) -> None:
    """Link records visibility."""
    engine = library_project.add_library("engine", sources=["src/engine.cpp"])
    math_lib = library_project.add_library("math", sources=["src/engine.cpp"])
    app = library_project.add_executable("app", sources=["src/main.cpp"])
    engine.link(math_lib, public=True)
    app.link(engine)
    model = library_project.freeze()
    engine_model = next(lib for lib in model.libraries if lib.name == "engine")
    assert engine_model.links[0].target == "math"
    assert engine_model.links[0].public is True
    assert model.executables[0].links[0].public is False


def test_link_cycle_detected_with_path(library_project: Project) -> None:
    """Link cycle detected with path."""
    alpha = library_project.add_library("alpha", sources=["src/engine.cpp"])
    beta = library_project.add_library("beta", sources=["src/engine.cpp"])
    alpha.link(beta)
    beta.link(alpha)
    with pytest.raises(ConfigurationError, match="alpha -> beta -> alpha"):
        library_project.freeze()


def test_link_to_foreign_library_rejected(
    project_dir: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Link to foreign library rejected."""
    other_dir = tmp_path_factory.mktemp("other")
    (other_dir / "lib.cpp").write_text("", encoding="utf-8")
    other_project = Project("other", root=other_dir)
    foreign = other_project.add_library("foreign", sources=["lib.cpp"])

    project = Project("demo", root=project_dir)
    app = project.add_executable("app", sources=["src/main.cpp"])
    app.link(foreign)
    with pytest.raises(ConfigurationError, match="not a library of this project"):
        project.freeze()


def test_link_rejects_non_library(library_project: Project) -> None:
    """Link rejects non library."""
    app = library_project.add_executable("app", sources=["src/main.cpp"])
    with pytest.raises(ConfigurationError, match="can only link Library"):
        app.link("engine")  # type: ignore[arg-type]


def test_glob_sources_expanded_and_sorted(library_project: Project) -> None:
    """Glob sources expanded and sorted."""
    (library_project.root / "src" / "audio.cpp").write_text("", encoding="utf-8")
    library_project.add_library("engine", sources=["src/*.cpp"])
    model = library_project.freeze()
    names = [source.as_posix() for source in model.libraries[0].sources]
    assert names == ["src/audio.cpp", "src/engine.cpp", "src/main.cpp"]


def test_empty_glob_is_a_configuration_error(library_project: Project) -> None:
    """Empty glob is a configuration error."""
    library_project.add_library("engine", sources=["src/*.cxx"])
    with pytest.raises(ConfigurationError, match=r"matched no\s+files"):
        library_project.freeze()


def test_define_and_compile_options(library_project: Project) -> None:
    """Define and compile options."""
    app = library_project.add_executable("app", sources=["src/main.cpp"])
    app.define("GAME_MAX_PLAYERS", 8)
    app.define("USE_AUDIO")
    app.compile_options("-march=native", when="gcc|clang")
    model = library_project.freeze()
    target = model.executables[0]
    assert (target.defines[0].name, target.defines[0].value) == ("GAME_MAX_PLAYERS", "8")
    assert target.defines[1].value is None
    assert target.compile_options[0].flags == ("-march=native",)
    when = target.compile_options[0].when
    assert when is not None
    assert when.kind is WhenKind.COMPILER
    assert when.names == ("GNU", "Clang", "AppleClang")


def test_unknown_when_compiler_rejected(library_project: Project) -> None:
    """Unknown when compiler rejected."""
    app = library_project.add_executable("app", sources=["src/main.cpp"])
    with pytest.raises(ConfigurationError, match="Unknown compiler 'icc'"):
        app.compile_options("-fast", when="icc")


def test_unknown_warnings_preset_rejected(project_dir: Path) -> None:
    """Unknown warnings preset rejected."""
    project = Project("demo", warnings="pedantic", root=project_dir)
    project.add_executable("app", sources=["src/main.cpp"])
    with pytest.raises(ConfigurationError, match="Unknown warnings preset"):
        project.freeze()
