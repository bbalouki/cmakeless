# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Parse CMake and compiler output into structured diagnostics.

The single biggest quality-of-life difference over raw CMake is how it feels
to fail: instead of a wall of text, the driver surfaces the first real errors
with file and line attached.
"""

from __future__ import annotations

import re

from cmakeless.errors import Diagnostic

# CMake's own configure-time failures: "CMake Error at CMakeLists.txt:12 (add_executable):"
_CMAKE_ERROR = re.compile(
    r"""
    ^CMake\ Error(?:\ at\ (?P<file>[^:\n]+):(?P<line>\d+))?
    (?:\ \((?P<command>[^)]+)\))?
    :\s*(?P<message>.*)$
    """,
    re.VERBOSE,
)

# GCC/Clang style: "src/main.cpp:5:10: error: use of undeclared identifier 'foo'".
# The optional drive-letter prefix keeps Windows paths like C:/src/main.cpp whole.
_GCC_CLANG_ERROR = re.compile(
    r"^(?P<file>(?:[A-Za-z]:)?[^:\n]+):(?P<line>\d+):(?:\d+:)?\s*(?:fatal\s+)?error:\s*(?P<message>.+)$"
)

# MSVC style: "src\main.cpp(5): error C2065: 'foo': undeclared identifier"
_MSVC_ERROR = re.compile(
    r"^(?P<file>[^(\n]+)\((?P<line>\d+)\)\s*:\s*(?:fatal\s+)?error\s+\w+:\s*(?P<message>.+)$"
)

# Linkers rarely give a file:line; keep the message anyway.
_LINKER_ERROR = re.compile(
    r"^.*(?:undefined reference to|unresolved external symbol|ld returned|LNK\d+).*$"
)

_MAX_DIAGNOSTICS = 10

_CONTINUATION_SENTINEL = "(see following lines)"


def extract_diagnostics(output: str) -> tuple[Diagnostic, ...]:
    """Pull the real errors out of raw cmake/compiler output, in order.

    Args:
        output: The combined stdout and stderr of a cmake invocation.

    Returns:
        Up to ten recognized diagnostics, first error first; empty when
        nothing recognizable was found.
    """
    diagnostics: list[Diagnostic] = []
    in_cmake_continuation = False
    for raw_line in output.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            in_cmake_continuation = False
            continue
        in_cmake_continuation = _consume_line(line, diagnostics, in_cmake_continuation)
        if len(diagnostics) >= _MAX_DIAGNOSTICS:
            break
    return tuple(diagnostics)


def _consume_line(line: str, diagnostics: list[Diagnostic], in_continuation: bool) -> bool:
    """Classify one output line, appending to the diagnostics as needed.

    Args:
        line: The stripped output line to classify.
        diagnostics: The diagnostics collected so far; appended in place.
        in_continuation: Whether the previous lines belong to a CMake error
            block whose explanation is still being written.

    Returns:
        Whether following lines continue a CMake error block.
    """
    cmake_match = _CMAKE_ERROR.match(line)
    if cmake_match:
        message = cmake_match.group("message").strip()
        diagnostics.append(
            Diagnostic(
                file=cmake_match.group("file"),
                line=_to_int(cmake_match.group("line")),
                message=message or _CONTINUATION_SENTINEL,
            )
        )
        return not message
    if in_continuation and line.startswith("  ") and diagnostics:
        # CMake writes the actual explanation indented under the header.
        _extend_last_diagnostic(diagnostics, line.strip())
        return True
    diagnostic = _match_compiler_or_linker(line)
    if diagnostic is not None:
        diagnostics.append(diagnostic)
    return False


def _match_compiler_or_linker(line: str) -> Diagnostic | None:
    """Try the compiler and linker error patterns against one line.

    Args:
        line: The stripped output line to match.

    Returns:
        The parsed diagnostic, or None when the line is not an error.
    """
    for pattern in (_GCC_CLANG_ERROR, _MSVC_ERROR):
        compiler_match = pattern.match(line)
        if compiler_match:
            return Diagnostic(
                file=compiler_match.group("file").strip(),
                line=_to_int(compiler_match.group("line")),
                message=compiler_match.group("message").strip(),
            )
    if _LINKER_ERROR.match(line):
        return Diagnostic(file=None, line=None, message=line.strip())
    return None


def _extend_last_diagnostic(diagnostics: list[Diagnostic], text: str) -> None:
    """Fold a CMake continuation line into the newest diagnostic's message.

    Args:
        diagnostics: The diagnostics collected so far; the last is replaced.
        text: The continuation text with indentation stripped.
    """
    previous = diagnostics[-1]
    appended = text if previous.message == _CONTINUATION_SENTINEL else f"{previous.message} {text}"
    diagnostics[-1] = Diagnostic(file=previous.file, line=previous.line, message=appended)


def _to_int(value: str | None) -> int | None:
    """Convert an optional regex group to an optional int.

    Args:
        value: The matched digits, or None when the group did not match.

    Returns:
        The parsed integer, or None.
    """
    return int(value) if value is not None else None
