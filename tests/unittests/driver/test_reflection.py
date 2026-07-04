# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Reflection against the real CMake engine: functions, variables, targets."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from cmakeless.driver.reflection import _reflect_targets, reflect, reflect_work_dir
from cmakeless.errors import CMakeError

requires_cmake = pytest.mark.skipif(shutil.which("cmake") is None, reason="cmake is not on PATH")


def _write(path: Path, text: str) -> Path:
    """Write a small .cmake fixture file and return its path."""
    path.write_text(text, encoding="utf-8")
    return path


@requires_cmake
def test_reflect_discovers_functions_and_variables(tmp_path: Path) -> None:
    """Reflect discovers functions and variables."""
    cmake_file = _write(
        tmp_path / "helper.cmake",
        'set(HELPER_GREETING "hi")\n'
        "function(print_hello)\n"
        '    message(STATUS "hello")\n'
        "endfunction()\n",
    )
    reflection = reflect(
        "cmake",
        work_dir=tmp_path / "work",
        reference=str(cmake_file),
        is_file=True,
        cpp_std=20,
    )
    assert reflection.functions == ("print_hello",)
    assert reflection.variables == ("HELPER_GREETING",)
    assert reflection.variable_values == {"HELPER_GREETING": "hi"}


@requires_cmake
def test_reflect_never_leaks_its_own_bookkeeping_variables(tmp_path: Path) -> None:
    """Reflect never leaks its own bookkeeping variables into the discovered set.

    Regression test: get_cmake_property(... VARIABLES) snapshots whatever is
    defined at the moment it runs, so an earlier bookkeeping variable this
    same script set is indistinguishable from one the include() defined
    unless filtered back out.
    """
    cmake_file = _write(tmp_path / "empty.cmake", "# defines nothing\n")
    reflection = reflect(
        "cmake", work_dir=tmp_path / "work", reference=str(cmake_file), is_file=True, cpp_std=20
    )
    assert reflection.functions == ()
    assert reflection.variables == ()


@requires_cmake
def test_reflect_falls_back_to_configure_for_non_scriptable_commands(tmp_path: Path) -> None:
    """A file calling a non-scriptable command (add_library) still reflects.

    add_library() is rejected by cmake -P script mode, so this only
    succeeds if the configure fallback runs.
    """
    cmake_file = _write(
        tmp_path / "with_target.cmake",
        'add_library(reflected_iface INTERFACE)\nset(WITH_TARGET_MARKER "present")\n',
    )
    reflection = reflect(
        "cmake", work_dir=tmp_path / "work", reference=str(cmake_file), is_file=True, cpp_std=20
    )
    assert reflection.variables == ("WITH_TARGET_MARKER",)


@requires_cmake
def test_reflect_discovers_targets_best_effort(tmp_path: Path) -> None:
    """Reflect discovers targets best effort, using a real compiled target.

    A plain STATIC library, not an INTERFACE one: a compiled target's
    presence in the codemodel's "targets" array has been stable since File
    API codemodel v2 was introduced, unlike a build-rule-free target's
    presence under "abstractTargets", which depends on the codemodel minor
    version a given CMake ships (see test_reflect_may_discover_an_interface_
    library_target below for that best-effort case specifically).
    """
    source = tmp_path / "lib.cpp"
    source.write_text("void reflected_lib_fn() {}\n", encoding="utf-8")
    cmake_file = _write(
        tmp_path / "with_target.cmake",
        f'add_library(reflected_lib STATIC "{source.as_posix()}")\n',
    )
    reflection = reflect(
        "cmake", work_dir=tmp_path / "work", reference=str(cmake_file), is_file=True, cpp_std=20
    )
    assert reflection.targets == ("reflected_lib",)


@requires_cmake
def test_reflect_may_discover_an_interface_library_target(tmp_path: Path) -> None:
    """Reflect may discover an interface library target, CMake version allowing.

    A build-rule-free target (INTERFACE, ALIAS, IMPORTED) is reported under
    the codemodel's "abstractTargets" array, a File API addition newer than
    this project's CMake 3.25 floor; older CMake versions simply omit the
    key, and the best-effort probe reports no targets rather than failing.
    Either outcome is correct, so this only checks that nothing raises and
    a spurious other name is never reported.
    """
    cmake_file = _write(tmp_path / "with_target.cmake", "add_library(reflected_iface INTERFACE)\n")
    reflection = reflect(
        "cmake", work_dir=tmp_path / "work", reference=str(cmake_file), is_file=True, cpp_std=20
    )
    assert reflection.targets in ((), ("reflected_iface",))


@requires_cmake
def test_reflect_targets_failure_is_silent(tmp_path: Path) -> None:
    """A target probe that cannot configure reports no targets, without raising.

    Calls the target-discovery pass directly: this file's add_library() call
    has no sources, a hard CMake error in any context, so both the NONE and
    CXX probe attempts fail. The public reflect() couples functions/
    variables (which raises on failure) and targets (best-effort) so
    tightly that a fixture reaching this path through reflect() would also
    fail the required half first; this exercises the best-effort contract
    in isolation instead.
    """
    cmake_file = _write(tmp_path / "broken_target.cmake", "add_library(reflected_iface STATIC)\n")
    targets = _reflect_targets(
        "cmake",
        work_dir=tmp_path / "work",
        reference=str(cmake_file),
        is_file=True,
        module_path=None,
        cpp_std=20,
    )
    assert targets == ()


@requires_cmake
def test_reflect_raises_when_the_include_is_broken(tmp_path: Path) -> None:
    """Reflect raises when the include is broken beyond both fallbacks."""
    cmake_file = _write(tmp_path / "broken.cmake", "this_function_does_not_exist()\n")
    with pytest.raises(CMakeError, match="Reflecting"):
        reflect(
            "cmake",
            work_dir=tmp_path / "work",
            reference=str(cmake_file),
            is_file=True,
            cpp_std=20,
        )


@requires_cmake
def test_reflect_a_named_builtin_module(tmp_path: Path) -> None:
    """Reflect a named builtin module discovers its real functions."""
    reflection = reflect(
        "cmake",
        work_dir=tmp_path / "work",
        reference="CheckCXXCompilerFlag",
        is_file=False,
        cpp_std=20,
    )
    assert "check_cxx_compiler_flag" in reflection.functions


def test_reflect_work_dir_is_deterministic_and_unique(tmp_path: Path) -> None:
    """Reflect work dir is deterministic for the same key, unique across keys."""
    first = reflect_work_dir(tmp_path, "cmake/a.cmake")
    again = reflect_work_dir(tmp_path, "cmake/a.cmake")
    other = reflect_work_dir(tmp_path, "cmake/b.cmake")
    assert first == again
    assert first != other
    assert first.is_relative_to(tmp_path)
