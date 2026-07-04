# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""CMakeModule through the public API: project.include()/include_module()."""

from __future__ import annotations

from pathlib import Path

import pytest

from cmakeless import ConfigurationError, Project
from cmakeless.driver.reflection import ModuleReflection


@pytest.fixture
def build_project(project_dir: Path) -> Project:
    """A minimal buildable project with a real .cmake file on disk."""
    (project_dir / "cmake").mkdir()
    (project_dir / "cmake" / "helper.cmake").write_text("", encoding="utf-8")
    return Project("demo", root=project_dir)


def _mock_reflect(
    monkeypatch: pytest.MonkeyPatch,
    *,
    functions: tuple[str, ...] = (),
    variables: tuple[str, ...] = (),
    variable_values: dict[str, str] | None = None,
    targets: tuple[str, ...] = (),
) -> None:
    """Mock the reflection boundary (a true external: subprocess/cmake).

    Reflection genuinely needs real CMake; the driver-layer tests in
    tests/unittests/driver/test_reflection.py exercise it for real. Here we
    only need CMakeModule's own API surface, so the boundary is mocked,
    matching how test_commands.py needs no CMake for add_command().
    """
    reflection = ModuleReflection(
        functions=functions,
        variables=variables,
        variable_values=variable_values or {},
        targets=targets,
    )
    monkeypatch.setattr("cmakeless.api.project.resolve_tool", lambda tool: "cmake")
    monkeypatch.setattr("cmakeless.api.project.reflect", lambda *args, **kwargs: reflection)


def test_include_returns_a_handle_with_discovered_functions_and_variables(
    build_project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Include returns a handle with discovered functions and variables."""
    _mock_reflect(
        monkeypatch,
        functions=("print_summary",),
        variables=("GREETING",),
        variable_values={"GREETING": "hi"},
    )
    module = build_project.include("cmake/helper.cmake")
    assert module.functions == ("print_summary",)
    assert module.variables == ("GREETING",)
    assert module.targets == ()


def test_include_module_returns_a_handle(
    build_project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Include module returns a handle."""
    _mock_reflect(monkeypatch, functions=("check_cxx_compiler_flag",))
    module = build_project.include_module("CheckCXXCompilerFlag")
    assert module.functions == ("check_cxx_compiler_flag",)


def test_include_module_with_module_path(
    build_project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Include module accepts a module_path directory that exists."""
    (build_project.root / "cmake" / "modules").mkdir()
    _mock_reflect(monkeypatch, functions=("do_thing",))
    module = build_project.include_module("MyModule", module_path="cmake/modules")
    assert module.functions == ("do_thing",)


def test_call_accepts_a_known_function_case_insensitively(
    build_project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Call accepts a known function case insensitively."""
    _mock_reflect(monkeypatch, functions=("Print_Summary",))
    module = build_project.include("cmake/helper.cmake")
    module.call("print_summary", "hello")  # must not raise


def test_call_rejects_an_unknown_function(
    build_project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Call rejects an unknown function, listing what is available."""
    _mock_reflect(monkeypatch, functions=("print_summary",))
    module = build_project.include("cmake/helper.cmake")
    with pytest.raises(ConfigurationError, match="print_summary"):
        module.call("no_such_function")


def test_variable_returns_a_known_variables_value(
    build_project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Variable returns a known variable's value."""
    _mock_reflect(monkeypatch, variables=("GREETING",), variable_values={"GREETING": "hi"})
    module = build_project.include("cmake/helper.cmake")
    assert module.variable("GREETING") == "hi"


def test_variable_rejects_an_unknown_variable(
    build_project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Variable rejects an unknown variable, listing what is available."""
    _mock_reflect(monkeypatch, variables=("GREETING",), variable_values={"GREETING": "hi"})
    module = build_project.include("cmake/helper.cmake")
    with pytest.raises(ConfigurationError, match="GREETING"):
        module.variable("NO_SUCH_VARIABLE")


def test_include_freezes_into_the_model(
    build_project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Include freezes into the model as a FILE ModuleModel."""
    _mock_reflect(monkeypatch, functions=("print_summary",))
    build_project.include("cmake/helper.cmake")
    model = build_project.freeze()
    (module,) = model.modules
    assert module.reference == "cmake/helper.cmake"
    assert module.module_path is None


def test_calls_freeze_in_declaration_order_not_sorted(
    build_project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Calls freeze in declaration order, not sorted.

    Unlike add_command()/add_custom_target(), call order is never arbitrary:
    CMake function calls can have order-dependent side effects.
    """
    _mock_reflect(monkeypatch, functions=("zeta_fn", "alpha_fn"))
    module = build_project.include("cmake/helper.cmake")
    module.call("zeta_fn")
    module.call("alpha_fn")
    model = build_project.freeze()
    (frozen,) = model.modules
    assert [call.function for call in frozen.calls] == ["zeta_fn", "alpha_fn"]


def test_include_path_must_be_relative(build_project: Project) -> None:
    """Include path must be relative."""
    with pytest.raises(ConfigurationError, match="relative path"):
        build_project.include("/etc/evil.cmake")


def test_include_path_must_exist(build_project: Project) -> None:
    """Include path must exist."""
    with pytest.raises(ConfigurationError, match="does not exist"):
        build_project.include("cmake/does_not_exist.cmake")


def test_include_module_path_must_be_relative(build_project: Project) -> None:
    """Include module's module_path must be relative."""
    with pytest.raises(ConfigurationError, match="relative path"):
        build_project.include_module("SomeModule", module_path="/etc")


def test_include_module_path_must_exist(build_project: Project) -> None:
    """Include module's module_path must exist."""
    with pytest.raises(ConfigurationError, match="does not exist"):
        build_project.include_module("SomeModule", module_path="cmake/missing")
