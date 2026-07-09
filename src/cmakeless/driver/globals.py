# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Probes every CMake variable a real project() configure defines.

One throwaway configure, never a hand-written CMake-language parser:
platform variables (WIN32/UNIX/APPLE/ANDROID/...) and compiler variables
(CMAKE_CXX_COMPILER_ID, CMAKE_SIZEOF_VOID_P, ...) are only set as a side
effect of a real project() call with a language enabled, so unlike
reflection.py's include() probe (which can often stay in fast cmake -P
script mode), this always needs a real configure.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from cmakeless.driver.generators import select_generator
from cmakeless.emitter.toolchain_emitter import emit_toolchain
from cmakeless.errors import CMakeError
from cmakeless.model.nodes import ToolchainModel

_PROJECT_NAME = "_cmakeless_globals"
_TOOLCHAIN_FILE_NAME = "globals-toolchain.cmake"
_OUTPUT_NAME = "globals-output.txt"
_VARIABLE_TAG = "VARIABLE\t"
_VALUE_TAG = "VALUE\t"
# Our own dump script's bookkeeping variable, filtered back out of the
# result so it never masquerades as a real CMake variable.
_BOOKKEEPING_VARIABLE = "_cmakeless_globals_all"


def probe_globals(
    cmake_executable: str,
    *,
    work_dir: Path,
    cpp_std: int,
    toolchain: ToolchainModel | None,
) -> dict[str, str]:
    """Configure a throwaway project and dump every CMake variable it defines.

    Args:
        cmake_executable: Absolute path to cmake, already resolved.
        work_dir: Scratch directory for the throwaway project; created if
            missing.
        cpp_std: The real project's C++ standard, so the probe configures
            representatively.
        toolchain: A toolchain to configure with, generated into work_dir via
            the same emit_toolchain() the real build uses, or None for the
            host toolchain.

    Returns:
        Every CMake variable the configure defined, name to resolved value.

    Raises:
        CMakeError: When the throwaway configure fails.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    output_path = work_dir / _OUTPUT_NAME
    project_dir = work_dir / "probe"
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "CMakeLists.txt").write_text(
        _project_preamble(cpp_std) + _dump_script(output_path), encoding="utf-8"
    )
    build_dir = project_dir / "build"
    command, completed = _configure(cmake_executable, project_dir, build_dir, work_dir, toolchain)
    if completed.returncode != 0:
        raise CMakeError(
            f"Reading CMake's global variables failed: cmake exited with code "
            f"{completed.returncode}. {completed.stderr.strip()} Check that the "
            f"toolchain is valid and that CMake and a C++ compiler for "
            f"standard {cpp_std} are on PATH.",
            command=command,
            exit_code=completed.returncode,
        )
    return _parse_dump(output_path)


def _project_preamble(cpp_std: int) -> str:
    """Render the throwaway project's cmake_minimum_required() and project().

    Args:
        cpp_std: The C++ standard to configure CXX with.

    Returns:
        The preamble text, ending in a newline.
    """
    return (
        "cmake_minimum_required(VERSION 3.25)\n"
        f"project({_PROJECT_NAME} LANGUAGES CXX)\n"
        f"set(CMAKE_CXX_STANDARD {cpp_std})\n"
    )


def _dump_script(output_path: Path) -> str:
    """Render the CMake snippet that dumps every currently defined variable.

    Args:
        output_path: Where the snippet should write its plain-text findings.

    Returns:
        The script text, appended after the project preamble.
    """
    out = output_path.as_posix()
    return (
        f"get_cmake_property({_BOOKKEEPING_VARIABLE} VARIABLES)\n"
        f'file(WRITE "{out}" "")\n'
        f"foreach(_cmakeless_var IN LISTS {_BOOKKEEPING_VARIABLE})\n"
        f'    file(APPEND "{out}" "{_VARIABLE_TAG}${{_cmakeless_var}}\\n")\n'
        f'    file(APPEND "{out}" "{_VALUE_TAG}${{${{_cmakeless_var}}}}\\n")\n'
        "endforeach()\n"
    )


def _configure(
    cmake_executable: str,
    project_dir: Path,
    build_dir: Path,
    work_dir: Path,
    toolchain: ToolchainModel | None,
) -> tuple[list[str], subprocess.CompletedProcess[str]]:
    """Run the throwaway configure, generating a toolchain file first if given.

    Args:
        cmake_executable: Absolute path to cmake.
        project_dir: The throwaway project's source directory.
        build_dir: The throwaway project's build directory.
        work_dir: Scratch directory for a generated toolchain file, if any.
        toolchain: A toolchain to configure with, or None for the host.

    Returns:
        The command run and its result.
    """
    command = [
        cmake_executable,
        "-S",
        str(project_dir),
        "-B",
        str(build_dir),
        *select_generator(None).cmake_args,
        *_toolchain_args(work_dir, toolchain),
    ]
    return command, subprocess.run(command, capture_output=True, text=True, check=False)


def _toolchain_args(work_dir: Path, toolchain: ToolchainModel | None) -> tuple[str, ...]:
    """Generate and reference a toolchain file for the probe, when one is given.

    Args:
        work_dir: Scratch directory to write the generated toolchain file into.
        toolchain: The toolchain to configure with, or None for the host.

    Returns:
        A -DCMAKE_TOOLCHAIN_FILE argument, or an empty tuple for the host.
    """
    if toolchain is None:
        return ()
    toolchain_file = work_dir / _TOOLCHAIN_FILE_NAME
    text = emit_toolchain(toolchain, tool_version="probe", source_script="cmake_globals()")
    toolchain_file.write_text(text, encoding="utf-8")
    return (f"-DCMAKE_TOOLCHAIN_FILE={toolchain_file.as_posix()}",)


def _parse_dump(output_path: Path) -> dict[str, str]:
    """Parse the plain, CMakeless-controlled output the dump script wrote.

    This reads a fixed, tag-prefixed line format CMakeless's own wrapper
    script produces (see _dump_script); it is not a CMake-language parser.

    Args:
        output_path: The file the dump script wrote.

    Returns:
        Every discovered variable, name to resolved value, this probe's own
        bookkeeping variable excluded.
    """
    values: dict[str, str] = {}
    pending_variable: str | None = None
    for line in output_path.read_text(encoding="utf-8").splitlines():
        if line.startswith(_VARIABLE_TAG):
            name = line[len(_VARIABLE_TAG) :]
            pending_variable = None if name == _BOOKKEEPING_VARIABLE else name
        elif line.startswith(_VALUE_TAG) and pending_variable is not None:
            values[pending_variable] = line[len(_VALUE_TAG) :]
            pending_variable = None
    return values
