"""Project options: typed CMake cache variables."""

from __future__ import annotations

from pathlib import Path

import pytest

from cmakeless import ConfigurationError, Project
from cmakeless.api.options import Option
from cmakeless.api.when import When
from cmakeless.model.nodes import OptionType


def test_option_infers_bool_type_from_default() -> None:
    """Option infers bool type from default."""
    option = Option("GUI", default=True, script="cmakelessfile.py")
    assert option._freeze().value_type is OptionType.BOOL


def test_option_infers_bool_before_int_since_bool_is_an_int_subclass() -> None:
    """Option infers bool before int, since bool is an int subclass in Python."""
    option = Option("ENABLE", default=False, script="cmakelessfile.py")
    assert option._freeze().value_type is OptionType.BOOL


def test_option_infers_int_type_from_default() -> None:
    """Option infers int type from default."""
    option = Option("JOBS", default=4, script="cmakelessfile.py")
    assert option._freeze().value_type is OptionType.INT


def test_option_infers_string_type_from_default() -> None:
    """Option infers string type from default."""
    option = Option("BACKEND", default="vulkan", script="cmakelessfile.py")
    assert option._freeze().value_type is OptionType.STRING


def test_option_type_override_wins_over_inference() -> None:
    """Option type override wins over inference."""
    option = Option("FLAG", default=1, type=bool, script="cmakelessfile.py")
    assert option._freeze().value_type is OptionType.BOOL


def test_option_unsupported_default_type_rejected() -> None:
    """Option unsupported default type rejected."""
    with pytest.raises(ConfigurationError, match="unsupported"):
        Option("BAD", default=[1, 2], script="cmakelessfile.py")  # type: ignore[arg-type]


def test_project_option_returns_a_handle(project_dir: Path) -> None:
    """Project option returns a handle."""
    project = Project("demo", root=project_dir)
    option = project.option("MYLIB_BUILD_GUI", default=True, help="Build the Qt front-end")
    assert option.name == "MYLIB_BUILD_GUI"


def test_project_option_freezes_into_the_model(project_dir: Path) -> None:
    """Project option freezes into the model."""
    project = Project("demo", root=project_dir)
    project.option("MYLIB_BUILD_GUI", default=True, help="Build the Qt front-end")
    model = project.freeze()
    (option,) = model.options
    assert option.name == "MYLIB_BUILD_GUI"
    assert option.default is True
    assert option.help == "Build the Qt front-end"


def test_duplicate_option_name_rejected(project_dir: Path) -> None:
    """Duplicate option name rejected."""
    project = Project("demo", root=project_dir)
    project.option("GUI", default=True)
    project.option("GUI", default=False)
    with pytest.raises(ConfigurationError, match="Duplicate option name"):
        project.freeze()


def test_when_option_referencing_unknown_option_rejected(project_dir: Path) -> None:
    """A When.option() referencing an undeclared option is rejected at freeze time."""
    project = Project("demo", root=project_dir)
    app = project.add_executable("app", sources=["src/main.cpp"])
    app.define("HAS_GUI", when=When.option("NEVER_DECLARED"))
    with pytest.raises(ConfigurationError, match="never declared"):
        project.freeze()


def test_when_option_referencing_declared_option_passes(project_dir: Path) -> None:
    """A When.option() referencing a declared option passes."""
    project = Project("demo", root=project_dir)
    gui = project.option("MYLIB_BUILD_GUI", default=True)
    app = project.add_executable("app", sources=["src/main.cpp"])
    app.define("HAS_GUI", when=When.option(gui))
    project.freeze()
