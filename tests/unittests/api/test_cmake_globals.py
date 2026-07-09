# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""CMakeGlobals: the wrapper project.cmake_globals() returns."""

from __future__ import annotations

import pytest

from cmakeless import CMakeGlobals


def test_hasattr_is_true_for_a_discovered_variable() -> None:
    """hasattr() is true for a variable CMake actually defined."""
    result = CMakeGlobals({"WIN32": "1"})
    assert hasattr(result, "WIN32")
    assert result.WIN32 == "1"


def test_hasattr_is_false_for_an_undiscovered_variable() -> None:
    """hasattr() is false for a variable CMake never defined."""
    result = CMakeGlobals({})
    assert not hasattr(result, "ANDROID")


def test_attribute_access_raises_a_helpful_error() -> None:
    """Direct attribute access on an unset variable names it and suggests a fix."""
    result = CMakeGlobals({"WIN32": "1"})
    with pytest.raises(AttributeError, match="ANDROID"):
        _ = result.ANDROID


def test_contains_mirrors_hasattr() -> None:
    """The 'in' operator agrees with hasattr()."""
    result = CMakeGlobals({"WIN32": "1"})
    assert "WIN32" in result
    assert "ANDROID" not in result


def test_get_returns_the_value_when_defined() -> None:
    """get() returns the discovered value when CMake defined it."""
    result = CMakeGlobals({"CMAKE_CXX_COMPILER_ID": "Clang"})
    assert result.get("CMAKE_CXX_COMPILER_ID") == "Clang"


def test_get_returns_the_default_when_undefined() -> None:
    """get() falls back to its default without raising."""
    result = CMakeGlobals({})
    assert result.get("ANDROID") is None
    assert result.get("ANDROID", "unset") == "unset"


def test_repr_reports_the_variable_count() -> None:
    """repr() is a developer-facing summary, not a variable dump."""
    result = CMakeGlobals({"WIN32": "1", "MSVC": "1"})
    assert repr(result) == "CMakeGlobals(2 variables)"
