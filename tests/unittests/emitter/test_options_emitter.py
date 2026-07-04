# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Emitter coverage for project.option(): option() and CACHE variable declarations."""

from __future__ import annotations

from pathlib import Path

from cmakeless.emitter import emit_cmakelists
from cmakeless.model.nodes import ExecutableModel, OptionModel, OptionType, ProjectModel

FIXED_VERSION = "1.2.3"
GOLDEN_DIR = Path(__file__).parent / "golden"


def make_model(**overrides: object) -> ProjectModel:
    """Build a frozen project with the given field overrides."""
    fields: dict[str, object] = {
        "name": "demo",
        "version": "1.0.0",
        "cpp_std": 17,
        "root_dir": Path("/does/not/matter"),
        "source_script": "cmakelessfile.py",
    }
    fields.update(overrides)
    return ProjectModel(**fields)  # type: ignore[arg-type]


def test_bool_option_emits_option_command() -> None:
    """A bool option emits a plain option() command with its default and help text."""
    option = OptionModel(
        name="MYLIB_BUILD_GUI", default=True, value_type=OptionType.BOOL, help="Build the GUI"
    )
    text = emit_cmakelists(make_model(options=(option,)), tool_version=FIXED_VERSION)
    assert 'option(MYLIB_BUILD_GUI "Build the GUI" ON)' in text


def test_bool_option_default_false_emits_off() -> None:
    """A bool option defaulting to False emits OFF."""
    option = OptionModel(name="MYLIB_BUILD_GUI", default=False, value_type=OptionType.BOOL)
    text = emit_cmakelists(make_model(options=(option,)), tool_version=FIXED_VERSION)
    assert 'option(MYLIB_BUILD_GUI "" OFF)' in text


def test_int_option_emits_cache_string_variable() -> None:
    """An int option emits a set(... CACHE STRING ...) variable."""
    option = OptionModel(name="MYLIB_JOBS", default=4, value_type=OptionType.INT)
    text = emit_cmakelists(make_model(options=(option,)), tool_version=FIXED_VERSION)
    assert 'set(MYLIB_JOBS "4" CACHE STRING "")' in text


def test_string_option_emits_cache_string_variable() -> None:
    """A string option emits a set(... CACHE STRING ...) variable."""
    option = OptionModel(name="MYLIB_BACKEND", default="vulkan", value_type=OptionType.STRING)
    text = emit_cmakelists(make_model(options=(option,)), tool_version=FIXED_VERSION)
    assert 'set(MYLIB_BACKEND "vulkan" CACHE STRING "")' in text


def test_options_are_declared_before_targets() -> None:
    """Options are declared before targets, so generator expressions can reference them."""
    option = OptionModel(name="MYLIB_BUILD_GUI", default=True, value_type=OptionType.BOOL)
    app = ExecutableModel(name="app", sources=(Path("src/main.cpp"),))
    text = emit_cmakelists(
        make_model(options=(option,), executables=(app,)), tool_version=FIXED_VERSION
    )
    assert text.index("option(MYLIB_BUILD_GUI") < text.index("add_executable(app)")


def test_no_options_emits_nothing() -> None:
    """No options emits nothing."""
    text = emit_cmakelists(make_model(), tool_version=FIXED_VERSION)
    assert "option(" not in text
    assert "CACHE STRING" not in text


def test_options_sorted_by_name_for_determinism() -> None:
    """Options sorted by name for determinism."""
    first = OptionModel(name="ZEBRA", default=True, value_type=OptionType.BOOL)
    second = OptionModel(name="ALPHA", default=True, value_type=OptionType.BOOL)
    text = emit_cmakelists(make_model(options=(first, second)), tool_version=FIXED_VERSION)
    assert text.index("ALPHA") < text.index("ZEBRA")


def test_golden_options_file() -> None:
    """Golden options file."""
    options = (
        OptionModel(
            name="MYLIB_BUILD_GUI",
            default=True,
            value_type=OptionType.BOOL,
            help="Build the Qt front-end",
        ),
        OptionModel(name="MYLIB_JOBS", default=4, value_type=OptionType.INT),
    )
    model = make_model(name="options_demo", options=options)
    text = emit_cmakelists(model, tool_version=FIXED_VERSION)
    assert text == (GOLDEN_DIR / "options.cmake").read_text(encoding="utf-8")
