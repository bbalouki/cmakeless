# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Emitter coverage for precompiled headers and unity builds."""

from __future__ import annotations

from pathlib import Path

from cmakeless.emitter import emit_cmakelists
from cmakeless.model.nodes import ExecutableModel, ProjectModel

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


def test_system_pch_header_is_emitted_verbatim() -> None:
    """A system pch header in angle brackets is emitted verbatim, unquoted."""
    app = ExecutableModel(name="app", sources=(Path("src/main.cpp"),), pch_headers=("<vector>",))
    text = emit_cmakelists(make_model(executables=(app,)), tool_version=FIXED_VERSION)
    assert "target_precompile_headers(app PRIVATE\n    <vector>\n)" in text


def test_project_relative_pch_header_is_quoted() -> None:
    """A project-relative pch header is quoted."""
    app = ExecutableModel(name="app", sources=(Path("src/main.cpp"),), pch_headers=("src/pch.hpp",))
    text = emit_cmakelists(make_model(executables=(app,)), tool_version=FIXED_VERSION)
    assert 'target_precompile_headers(app PRIVATE\n    "src/pch.hpp"\n)' in text


def test_no_pch_block_without_headers() -> None:
    """No pch block without headers."""
    app = ExecutableModel(name="app", sources=(Path("src/main.cpp"),))
    text = emit_cmakelists(make_model(executables=(app,)), tool_version=FIXED_VERSION)
    assert "target_precompile_headers" not in text


def test_unity_emits_the_target_property() -> None:
    """Unity emits the target property."""
    app = ExecutableModel(name="app", sources=(Path("src/main.cpp"),), unity=True)
    text = emit_cmakelists(make_model(executables=(app,)), tool_version=FIXED_VERSION)
    assert "set_target_properties(app PROPERTIES UNITY_BUILD ON)" in text


def test_no_unity_property_when_not_requested() -> None:
    """No unity property when not requested."""
    app = ExecutableModel(name="app", sources=(Path("src/main.cpp"),))
    text = emit_cmakelists(make_model(executables=(app,)), tool_version=FIXED_VERSION)
    assert "UNITY_BUILD" not in text


def test_golden_pch_unity_file() -> None:
    """Golden pch unity file."""
    app = ExecutableModel(
        name="app",
        sources=(Path("src/main.cpp"),),
        pch_headers=("<vector>", "src/pch.hpp"),
        unity=True,
    )
    model = make_model(name="pch_unity_demo", executables=(app,))
    text = emit_cmakelists(model, tool_version=FIXED_VERSION)
    assert text == (GOLDEN_DIR / "pch_unity.cmake").read_text(encoding="utf-8")
