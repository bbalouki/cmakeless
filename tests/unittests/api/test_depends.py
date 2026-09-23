"""target.depends(): specs, deduplication, conflicts, and link edges."""

from __future__ import annotations

from pathlib import Path

import pytest

from cmakeless import Project
from cmakeless.errors import ConfigurationError, DependencyError
from cmakeless.model.nodes import LinkModel


def make_project(project_dir: Path) -> Project:
    """A minimal project rooted at the shared on-disk layout."""
    return Project("demo", version="1.0.0", cpp_std=20, root=project_dir)


def test_depends_registers_the_package_and_links_its_targets(project_dir: Path) -> None:
    """Depends registers the package and links its targets."""
    project = make_project(project_dir)
    app = project.add_executable("app", sources=["src/main.cpp"])
    dependency = app.depends("fmt/10.2.1")
    assert dependency.name == "fmt"
    assert dependency.version == "10.2.1"
    model = project.freeze()
    assert model.dependencies[0].name == "fmt"
    assert LinkModel(target="fmt::fmt", public=False, external=True) in (model.executables[0].links)


def test_public_dependency_propagates_to_consumers(project_dir: Path) -> None:
    """Public dependency propagates to consumers."""
    project = make_project(project_dir)
    engine = project.add_library("engine", sources=["src/main.cpp"])
    engine.depends("fmt/10.2.1", public=True)
    model = project.freeze()
    assert LinkModel(target="fmt::fmt", public=True, external=True) in model.libraries[0].links


def test_same_spec_from_two_targets_is_one_dependency(project_dir: Path) -> None:
    """Same spec from two targets is one dependency."""
    project = make_project(project_dir)
    app = project.add_executable("app", sources=["src/main.cpp"])
    engine = project.add_library("engine", sources=["src/main.cpp"])
    first = app.depends("fmt/10.2.1")
    second = engine.depends("fmt/10.2.1")
    assert first is second
    assert len(project.dependencies) == 1


def test_conflicting_versions_are_rejected_immediately(project_dir: Path) -> None:
    """Conflicting versions are rejected immediately."""
    project = make_project(project_dir)
    app = project.add_executable("app", sources=["src/main.cpp"])
    app.depends("fmt/10.2.1")
    with pytest.raises(ConfigurationError, match=r"fmt/10\.2\.1"):
        app.depends("fmt/11.0.0")


def test_conflicting_overrides_are_rejected(project_dir: Path) -> None:
    """Conflicting overrides are rejected."""
    project = make_project(project_dir)
    app = project.add_executable("app", sources=["src/main.cpp"])
    app.depends("boost/1.84.0", components=["asio"])
    with pytest.raises(ConfigurationError, match="different components or overrides"):
        app.depends("boost/1.84.0", components=["beast"])


@pytest.mark.parametrize("bad_spec", ["fmt", "fmt/", "/10.2.1", "fmt/10/1", ""])
def test_malformed_specs_are_rejected(project_dir: Path, bad_spec: str) -> None:
    """Malformed specs are rejected."""
    project = make_project(project_dir)
    app = project.add_executable("app", sources=["src/main.cpp"])
    with pytest.raises(ConfigurationError, match="name/version"):
        app.depends(bad_spec)


def test_unknown_package_fails_at_the_depends_call(project_dir: Path) -> None:
    """Unknown package fails at the depends call."""
    project = make_project(project_dir)
    app = project.add_executable("app", sources=["src/main.cpp"])
    with pytest.raises(DependencyError, match="obscurelib"):
        app.depends("obscurelib/1.0")


def test_unknown_package_works_with_explicit_overrides(project_dir: Path) -> None:
    """Unknown package works with explicit overrides."""
    project = make_project(project_dir)
    app = project.add_executable("app", sources=["src/main.cpp"])
    app.depends(
        "obscurelib/1.0",
        targets=["obscure::lib"],
        url="https://example.com/obscure-1.0.tar.gz",
        sha256="feed" * 16,
    )
    model = project.freeze()
    assert model.dependencies[0].cmake_name == "obscurelib"
    assert LinkModel(target="obscure::lib", external=True) in model.executables[0].links


def test_components_expand_into_link_edges(project_dir: Path) -> None:
    """Components expand into link edges."""
    project = make_project(project_dir)
    app = project.add_executable("app", sources=["src/main.cpp"])
    app.depends("boost/1.84.0", components=["asio", "beast"])
    links = project.freeze().executables[0].links
    assert LinkModel(target="Boost::asio", external=True) in links
    assert LinkModel(target="Boost::beast", external=True) in links


def test_frozen_dependencies_are_sorted_by_name(project_dir: Path) -> None:
    """Frozen dependencies are sorted by name."""
    project = make_project(project_dir)
    app = project.add_executable("app", sources=["src/main.cpp"])
    app.depends("spdlog/1.14.1")
    app.depends("fmt/10.2.1")
    model = project.freeze()
    assert [dep.name for dep in model.dependencies] == ["fmt", "spdlog"]


def test_link_error_now_points_at_depends(project_dir: Path) -> None:
    """Link error now points at depends."""
    project = make_project(project_dir)
    app = project.add_executable("app", sources=["src/main.cpp"])
    with pytest.raises(ConfigurationError, match=r'depends\("fmt/10\.2\.1"\)'):
        app.link("fmt")  # type: ignore[arg-type]


def test_package_manager_flows_into_the_model(project_dir: Path) -> None:
    """Package manager flows into the model."""
    project = make_project(project_dir)
    project.package_manager = "vcpkg"
    assert project.freeze().package_manager == "vcpkg"


def test_unknown_package_manager_is_rejected_at_freeze(project_dir: Path) -> None:
    """Unknown package manager is rejected at freeze."""
    project = make_project(project_dir)
    project.package_manager = "npm"
    with pytest.raises(ConfigurationError, match="Unknown package manager"):
        project.freeze()
