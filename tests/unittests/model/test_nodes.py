# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""The model layer must be immutable, pure data."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from cmakeless.model.nodes import ExecutableModel, ProjectModel


def make_project_model(**overrides: object) -> ProjectModel:
    """Build a valid ProjectModel, overriding any field by name."""
    defaults: dict[str, object] = {
        "name": "demo",
        "version": "1.0.0",
        "cpp_std": 20,
        "root_dir": Path("/tmp/demo"),
        "source_script": "cmakelessfile.py",
        "executables": (),
    }
    defaults.update(overrides)
    return ProjectModel(**defaults)  # type: ignore[arg-type]


def test_executable_model_is_frozen() -> None:
    """Executable model is frozen."""
    model = ExecutableModel(name="app", sources=(Path("main.cpp"),))
    with pytest.raises(dataclasses.FrozenInstanceError):
        model.name = "other"  # type: ignore[misc]


def test_project_model_is_frozen() -> None:
    """Project model is frozen."""
    model = make_project_model()
    with pytest.raises(dataclasses.FrozenInstanceError):
        model.name = "other"  # type: ignore[misc]


def test_models_hold_tuples_not_lists() -> None:
    """Models hold tuples not lists."""
    model = make_project_model(
        executables=(ExecutableModel(name="app", sources=(Path("main.cpp"),)),)
    )
    assert isinstance(model.executables, tuple)
    assert isinstance(model.executables[0].sources, tuple)


def test_new_optional_fields_default_to_empty() -> None:
    """The escape-hatch and build-config fields default to no-op values."""
    model = make_project_model()
    assert model.optimize is None
    assert model.lto is False
    assert model.raw_cmake_files == ()
    executable = ExecutableModel(name="app", sources=(Path("main.cpp"),))
    assert executable.raw_cmake == ()
