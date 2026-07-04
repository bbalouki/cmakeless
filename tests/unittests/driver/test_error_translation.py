# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Raw cmake/compiler output must become structured diagnostics."""

from __future__ import annotations

from cmakeless.driver.error_translation import extract_diagnostics

GCC_OUTPUT = """\
[1/2] Building CXX object CMakeFiles/app.dir/src/main.cpp.obj
src/main.cpp:5:10: error: 'foo' was not declared in this scope
    5 |     foo();
warning: unused variable 'bar'
"""

CLANG_FATAL = """\
src/main.cpp:1:10: fatal error: 'missing.hpp' file not found
"""

MSVC_OUTPUT = r"""
src\main.cpp(5): error C2065: 'foo': undeclared identifier
src\main.cpp(9): warning C4100: unreferenced formal parameter
"""

CMAKE_OUTPUT = """\
-- Configuring incomplete, errors occurred!
CMake Error at CMakeLists.txt:12 (add_executable):
  Cannot find source file:

    src/nope.cpp
"""

LINKER_OUTPUT = """\
main.cpp:(.text+0x5): undefined reference to `foo()'
collect2: error: ld returned 1 exit status
"""


def test_gcc_style_errors() -> None:
    """Gcc style errors."""
    diagnostics = extract_diagnostics(GCC_OUTPUT)
    assert len(diagnostics) == 1
    assert diagnostics[0].file == "src/main.cpp"
    assert diagnostics[0].line == 5
    assert "'foo' was not declared" in diagnostics[0].message


def test_clang_fatal_error() -> None:
    """Clang fatal error."""
    diagnostics = extract_diagnostics(CLANG_FATAL)
    assert diagnostics[0].line == 1
    assert "file not found" in diagnostics[0].message


def test_msvc_style_errors_ignore_warnings() -> None:
    """Msvc style errors ignore warnings."""
    diagnostics = extract_diagnostics(MSVC_OUTPUT)
    assert len(diagnostics) == 1
    assert diagnostics[0].file == "src\\main.cpp"
    assert "undeclared identifier" in diagnostics[0].message


def test_cmake_error_with_continuation_lines() -> None:
    """Cmake error with continuation lines."""
    diagnostics = extract_diagnostics(CMAKE_OUTPUT)
    assert diagnostics[0].file == "CMakeLists.txt"
    assert diagnostics[0].line == 12
    assert "Cannot find source file" in diagnostics[0].message


def test_linker_errors_are_kept() -> None:
    """Linker errors are kept."""
    diagnostics = extract_diagnostics(LINKER_OUTPUT)
    assert any("undefined reference" in diag.message for diag in diagnostics)


def test_clean_output_yields_nothing() -> None:
    """Clean output yields nothing."""
    assert extract_diagnostics("-- Configuring done\n-- Generating done\n") == ()


def test_diagnostic_str_includes_location() -> None:
    """Diagnostic str includes location."""
    diagnostics = extract_diagnostics(GCC_OUTPUT)
    assert str(diagnostics[0]).startswith("src/main.cpp:5: ")
