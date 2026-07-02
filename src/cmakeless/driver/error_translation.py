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


def extract_diagnostics(output: str) -> tuple[Diagnostic, ...]:
    """Pull the real errors out of raw cmake/compiler output, in order."""
    diagnostics: list[Diagnostic] = []
    continuation_of_cmake_error = False
    for raw_line in output.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continuation_of_cmake_error = False
            continue
        cmake_match = _CMAKE_ERROR.match(line)
        if cmake_match:
            diagnostics.append(
                Diagnostic(
                    file=cmake_match.group("file"),
                    line=_to_int(cmake_match.group("line")),
                    message=cmake_match.group("message").strip() or "(see following lines)",
                )
            )
            continuation_of_cmake_error = not cmake_match.group("message").strip()
            continue
        if continuation_of_cmake_error and line.startswith("  ") and diagnostics:
            # CMake writes the actual explanation indented under the header.
            previous = diagnostics[-1]
            appended = (
                line.strip()
                if previous.message == "(see following lines)"
                else f"{previous.message} {line.strip()}"
            )
            diagnostics[-1] = Diagnostic(file=previous.file, line=previous.line, message=appended)
            continue
        for pattern in (_GCC_CLANG_ERROR, _MSVC_ERROR):
            compiler_match = pattern.match(line)
            if compiler_match:
                diagnostics.append(
                    Diagnostic(
                        file=compiler_match.group("file").strip(),
                        line=_to_int(compiler_match.group("line")),
                        message=compiler_match.group("message").strip(),
                    )
                )
                break
        else:
            if _LINKER_ERROR.match(line):
                diagnostics.append(Diagnostic(file=None, line=None, message=line.strip()))
        if len(diagnostics) >= _MAX_DIAGNOSTICS:
            break
    return tuple(diagnostics)


def _to_int(value: str | None) -> int | None:
    return int(value) if value is not None else None
