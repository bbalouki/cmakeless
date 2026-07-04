# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""The add_python_module() builder: backends, links, and freeze output."""

from __future__ import annotations

from pathlib import Path

import pytest

from cmakeless import ConfigurationError, Project, PythonModule
from cmakeless._constants import MIN_PYTHON_VERSION


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


def test_default_binding_is_pybind11(module_project: Project) -> None:
    """The default binding backend is pybind11 when none is given."""
    module = module_project.add_python_module("core", sources=["src/bindings.cpp"])
    model = module_project.freeze()
    assert module.binding == "pybind11"
    assert model.python_modules[0].binding == "pybind11"
    assert [dep.name for dep in model.dependencies] == ["pybind11"]


def test_target_raw_cmake_freezes_in_order(module_project: Project) -> None:
    """Target raw_cmake snippets freeze verbatim, in the order added."""
    module = module_project.add_python_module("core", sources=["src/bindings.cpp"])
    module.raw_cmake('set_target_properties(core PROPERTIES PREFIX "")')
    module.raw_cmake("target_compile_definitions(core PRIVATE FAST=1)")
    model = module_project.freeze()
    assert model.python_modules[0].raw_cmake == (
        'set_target_properties(core PROPERTIES PREFIX "")',
        "target_compile_definitions(core PRIVATE FAST=1)",
    )


def test_empty_raw_cmake_is_rejected(module_project: Project) -> None:
    """An empty raw_cmake snippet fails at the call site."""
    module = module_project.add_python_module("core", sources=["src/bindings.cpp"])
    with pytest.raises(ConfigurationError, match="Empty raw_cmake"):
        module.raw_cmake("   ")


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


def test_python_version_defaults_to_the_minimum_supported_version(
    module_project: Project,
) -> None:
    """No python_version= override freezes to CMakeless's own floor."""
    module_project.add_python_module("core", sources=["src/bindings.cpp"])
    model = module_project.freeze()
    assert model.python_modules[0].python_version == MIN_PYTHON_VERSION


def test_python_version_override_freezes_onto_the_model(module_project: Project) -> None:
    """An explicit python_version= freezes onto the model unchanged."""
    module_project.add_python_module("core", sources=["src/bindings.cpp"], python_version="3.13")
    model = module_project.freeze()
    assert model.python_modules[0].python_version == "3.13"


def test_malformed_python_version_fails_at_the_call_site(module_project: Project) -> None:
    """A python_version= that is not "MAJOR.MINOR" fails immediately, not at freeze."""
    with pytest.raises(ConfigurationError, match="python_version"):
        module_project.add_python_module("core", sources=["src/bindings.cpp"], python_version="3")
    with pytest.raises(ConfigurationError, match="python_version"):
        module_project.add_python_module(
            "core2", sources=["src/bindings.cpp"], python_version="abc.def"
        )
