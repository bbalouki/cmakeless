"""The add_python_module() builder: backends, links, and freeze output."""

from __future__ import annotations

from pathlib import Path

import pytest

from cmakeless import ConfigurationError, Project, PythonModule


@pytest.fixture
def module_project(project_dir: Path) -> Project:
    """A project with one library and one on-disk binding source."""
    (project_dir / "src" / "bindings.cpp").write_text("// bindings\n", encoding="utf-8")
    project = Project("demo", cpp_std=17, root=project_dir)
    project.add_library("engine", sources=["src/main.cpp"])
    return project


def test_add_python_module_registers_the_binding_dependency(module_project: Project) -> None:
    """Add python module registers the binding dependency."""
    module_project.add_python_module("core", sources=["src/bindings.cpp"], binding="nanobind")
    assert [dep.name for dep in module_project.dependencies] == ["nanobind"]


def test_pybind11_backend_registers_the_pybind11_package(module_project: Project) -> None:
    """Pybind11 backend registers the pybind11 package."""
    module_project.add_python_module("core", sources=["src/bindings.cpp"], binding="pybind11")
    model = module_project.freeze()
    assert [dep.name for dep in model.dependencies] == ["pybind11"]
    assert model.python_modules[0].binding == "pybind11"


def test_binding_is_not_a_manual_link_edge(module_project: Project) -> None:
    """Binding is not a manual link edge."""
    module = module_project.add_python_module("core", sources=["src/bindings.cpp"])
    model = module_project.freeze()
    # The <binding>_add_module command links the backend, so no external link.
    assert model.python_modules[0].links == ()
    assert isinstance(module, PythonModule)


def test_module_links_project_libraries(module_project: Project) -> None:
    """Module links project libraries."""
    engine = module_project._libraries[0]
    module = module_project.add_python_module("core", sources=["src/bindings.cpp"])
    module.link(engine)
    model = module_project.freeze()
    assert model.python_modules[0].links[0].target == "engine"


def test_unknown_binding_fails_at_the_call_site(module_project: Project) -> None:
    """Unknown binding fails at the call site."""
    with pytest.raises(ConfigurationError, match="cython"):
        module_project.add_python_module(
            "core",
            sources=["src/bindings.cpp"],
            binding="cython",  # type: ignore[arg-type]
        )


def test_module_appears_in_all_targets(module_project: Project) -> None:
    """Module appears in all targets."""
    module_project.add_python_module("core", sources=["src/bindings.cpp"])
    model = module_project.freeze()
    assert "core" in {target.name for target in model.all_targets()}


def test_module_name_collides_with_target_names(module_project: Project) -> None:
    """Module name collides with target names."""
    module_project.add_python_module("engine", sources=["src/bindings.cpp"])
    with pytest.raises(ConfigurationError, match="Duplicate target name"):
        module_project.freeze()


def test_stubs_and_install_flags_freeze(module_project: Project) -> None:
    """Stubs and install flags freeze."""
    module_project.add_python_module(
        "core", sources=["src/bindings.cpp"], stubs=False, install=False
    )
    model = module_project.freeze()
    assert model.python_modules[0].stubs is False
    assert model.python_modules[0].install_to_environment is False


def test_sanitize_attribute_freezes_sorted(module_project: Project) -> None:
    """Sanitize attribute freezes sorted."""
    module = module_project.add_python_module("core", sources=["src/bindings.cpp"])
    module.sanitize = ["undefined", "address", "undefined"]
    model = module_project.freeze()
    assert model.python_modules[0].sanitize == ("address", "undefined")
