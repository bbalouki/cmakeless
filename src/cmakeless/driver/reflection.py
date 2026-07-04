# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Reflects a CMake include(): its functions, variables, and targets.

Two real CMake runs, never a hand-written CMake-language parser:

- Functions and variables (required) come from a throwaway `cmake -P`
  script run: CMake's own COMMANDS/VARIABLES global properties are
  snapshotted before and after the include(), and the difference is the
  include's own additions. No project, no compiler, needed.
- Targets (best-effort) come from a throwaway configure of a minimal
  project that does nothing but the same include(), read back through the
  same File API codemodel query project.targets_info() already uses. Some
  includes only work inside their real parent project; when the throwaway
  configure fails, targets come back empty rather than raising.
"""

from __future__ import annotations

import hashlib
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from cmakeless.driver.file_api import read_reply, write_query
from cmakeless.driver.generators import select_generator
from cmakeless.errors import CMakeError

_REFLECT_PROJECT_NAME = "_cmakeless_reflect"
_SCRIPT_NAME = "reflect.cmake"
_OUTPUT_NAME = "reflect-output.txt"
_FUNCTION_TAG = "FUNCTION\t"
_VARIABLE_TAG = "VARIABLE\t"
_VALUE_TAG = "VALUE\t"

# Names that must never count as "newly defined by the include", regardless
# of CMake version: our own script's bookkeeping variables (see below), plus
# CMake's own automatic context variables that come and go around an
# include() call rather than being defined by the included file itself.
# get_cmake_property(... VARIABLES) snapshots whatever is defined at the
# moment it runs, so a variable this same script set on an earlier line
# (including an earlier snapshot's own result variable), or one CMake sets
# while processing the included file, is indistinguishable from one the
# include() itself defined unless filtered back out; doing that in Python is
# simpler and more robust than trying to order the script so nothing else is
# ever visible to a later snapshot, and it does not depend on which of these
# automatic variables a given CMake version happens to set.
_INTERNAL_VARIABLE_NAMES = frozenset(
    {
        "_cmakeless_before_functions",
        "_cmakeless_before_variables",
        "_cmakeless_after_functions",
        "_cmakeless_after_variables",
        "CMAKE_PARENT_LIST_FILE",
        "CMAKE_CURRENT_LIST_FILE",
        "CMAKE_CURRENT_LIST_DIR",
        "CMAKE_CURRENT_LIST_LINE",
    }
)


@dataclass(frozen=True, slots=True)
class ModuleReflection:
    """Everything CMake reported a project.include()/include_module() call defines.

    Attributes:
        functions: Function and macro names the include newly defined.
        variables: Variable names the include newly defined.
        variable_values: Each discovered variable's resolved value, keyed by
            name.
        targets: Target names the include defined, discovered best-effort;
            empty when the throwaway target probe could not configure.
    """

    functions: tuple[str, ...]
    variables: tuple[str, ...]
    variable_values: Mapping[str, str] = field(default_factory=dict)
    targets: tuple[str, ...] = ()


def reflect_work_dir(build_dir: Path, key: str) -> Path:
    """A unique scratch directory for one include()/include_module() reflection.

    Args:
        build_dir: The project's build directory; reflection scratch lives
            underneath it, so project.clean() reclaims it too.
        key: The reference being reflected (a path or a module name).

    Returns:
        A directory unique to this reference, so repeated or concurrent
        reflections of different includes never collide. Kept short: this
        path is a prefix of every throwaway probe's own build tree, and
        Windows' MAX_PATH limit is already a real constraint there.
    """
    slug = hashlib.sha256(key.encode("utf-8")).hexdigest()[:8]
    return build_dir / ".cmakeless-reflect" / slug


def reflect(
    cmake_executable: str,
    *,
    work_dir: Path,
    reference: str,
    is_file: bool,
    module_path: Path | None = None,
    cpp_std: int,
) -> ModuleReflection:
    """Reflect one include()'s functions, variables, and (best-effort) targets.

    Args:
        cmake_executable: Absolute path to cmake, already resolved.
        work_dir: Scratch directory for the throwaway script and configure;
            created if missing.
        reference: An absolute file path (is_file=True) or a bare module
            name (is_file=False) to include.
        is_file: True to include() a file path, False to include() a module
            name.
        module_path: An absolute directory to add to CMAKE_MODULE_PATH
            before including, or None.
        cpp_std: The real project's C++ standard, so the best-effort target
            probe configures representatively.

    Returns:
        The discovered functions, variables, and (best-effort) targets.

    Raises:
        CMakeError: When the required functions/variables reflection script
            fails to run.
    """
    functions, variables, values = _reflect_functions_and_variables(
        cmake_executable,
        work_dir=work_dir,
        reference=reference,
        is_file=is_file,
        module_path=module_path,
        cpp_std=cpp_std,
    )
    targets = _reflect_targets(
        cmake_executable,
        work_dir=work_dir,
        reference=reference,
        is_file=is_file,
        module_path=module_path,
        cpp_std=cpp_std,
    )
    return ModuleReflection(
        functions=functions, variables=variables, variable_values=values, targets=targets
    )


def _include_statement(*, reference: str, is_file: bool, module_path: Path | None) -> str:
    """Render the include() (and its CMAKE_MODULE_PATH setup) under reflection.

    Args:
        reference: An absolute file path (is_file=True) or a bare module
            name (is_file=False).
        is_file: True to include() a file path, False to include() a name.
        module_path: An absolute directory to add to CMAKE_MODULE_PATH
            first, or None.

    Returns:
        One or two CMake statements, newline-joined.
    """
    lines = []
    if module_path is not None:
        lines.append(f'list(APPEND CMAKE_MODULE_PATH "{module_path.as_posix()}")')
    if is_file:
        lines.append(f'include("{Path(reference).as_posix()}")')
    else:
        lines.append(f"include({reference})")
    return "\n".join(lines)


def _probe_generator_args() -> tuple[str, ...]:
    """The generator arguments a throwaway probe configure should use.

    Explicitly prefers Ninja, the same auto-selection the main pipeline
    uses: it needs no per-config subdirectories the way Visual Studio's
    MSBuild generator does, which matters because these probes live under
    an already-deep build/.cmakeless-reflect/<hash>/ scratch path, where
    Windows' MAX_PATH limit is otherwise easy to hit.

    Returns:
        The -G arguments, or an empty tuple when Ninja is not on PATH
        (falls back to CMake's own default generator).
    """
    return select_generator(None).cmake_args


def _project_preamble(cpp_std: int | None) -> str:
    """Render a throwaway project's cmake_minimum_required() and project().

    Args:
        cpp_std: The C++ standard to configure CXX with, or None for a
            LANGUAGES NONE project (no compiler needed, but unable to
            configure a real compiled target).

    Returns:
        The preamble text, ending in a newline.
    """
    languages = "CXX" if cpp_std is not None else "NONE"
    standard = f"set(CMAKE_CXX_STANDARD {cpp_std})\n" if cpp_std is not None else ""
    return (
        "cmake_minimum_required(VERSION 3.25)\n"
        f"project({_REFLECT_PROJECT_NAME} LANGUAGES {languages})\n"
        f"{standard}"
    )


def _reflection_script(output_path: Path, include_statement: str) -> str:
    """Render the throwaway cmake -P script that diffs COMMANDS/VARIABLES.

    Args:
        output_path: Where the script should write its plain-text findings.
        include_statement: The include() (and CMAKE_MODULE_PATH setup)
            under reflection.

    Returns:
        The complete script text.
    """
    out = output_path.as_posix()
    return (
        "get_cmake_property(_cmakeless_before_functions COMMANDS)\n"
        "get_cmake_property(_cmakeless_before_variables VARIABLES)\n"
        f"{include_statement}\n"
        "get_cmake_property(_cmakeless_after_functions COMMANDS)\n"
        "get_cmake_property(_cmakeless_after_variables VARIABLES)\n"
        "list(REMOVE_ITEM _cmakeless_after_functions ${_cmakeless_before_functions})\n"
        "list(REMOVE_ITEM _cmakeless_after_variables ${_cmakeless_before_variables})\n"
        f'file(WRITE "{out}" "")\n'
        "foreach(_cmakeless_fn IN LISTS _cmakeless_after_functions)\n"
        f'    file(APPEND "{out}" "{_FUNCTION_TAG}${{_cmakeless_fn}}\\n")\n'
        "endforeach()\n"
        "foreach(_cmakeless_var IN LISTS _cmakeless_after_variables)\n"
        f'    file(APPEND "{out}" "{_VARIABLE_TAG}${{_cmakeless_var}}\\n")\n'
        f'    file(APPEND "{out}" "{_VALUE_TAG}${{${{_cmakeless_var}}}}\\n")\n'
        "endforeach()\n"
    )


def _run_script_mode(
    cmake_executable: str, work_dir: Path, script: str
) -> tuple[list[str], subprocess.CompletedProcess[str]]:
    """Run the reflection script via cmake -P: fast, no project or compiler needed.

    Args:
        cmake_executable: Absolute path to cmake.
        work_dir: Scratch directory for the throwaway script.
        script: The reflection script's complete text.

    Returns:
        The command run and its result.
    """
    script_path = work_dir / _SCRIPT_NAME
    script_path.write_text(script, encoding="utf-8")
    command = [cmake_executable, "-P", str(script_path)]
    return command, subprocess.run(command, capture_output=True, text=True, check=False)


def _run_reflection_configure(
    cmake_executable: str, work_dir: Path, script: str, *, cpp_std: int | None
) -> tuple[list[str], subprocess.CompletedProcess[str]]:
    """Run the same reflection script inside a throwaway project's configure.

    Falls back to this when script mode rejects the include: some CMake
    commands (add_library(), add_executable(), ...) are "not scriptable"
    and only work inside a real project. Tried first with cpp_std=None
    (LANGUAGES NONE): fast, and sidesteps compiler detection (a real
    MAX_PATH hazard on Windows under an already-deep scratch path), which
    covers the common non-scriptable-but-compiler-free case (INTERFACE
    libraries, custom targets, install rules). An include that declares a
    real compiled target needs a second attempt with the real cpp_std.

    Args:
        cmake_executable: Absolute path to cmake.
        work_dir: Scratch directory for the throwaway project.
        script: The reflection script's complete text.
        cpp_std: The C++ standard for a LANGUAGES CXX retry, or None to
            configure with LANGUAGES NONE.

    Returns:
        The command run and its result.
    """
    project_dir = work_dir / "fn"
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "CMakeLists.txt").write_text(
        _project_preamble(cpp_std) + script, encoding="utf-8"
    )
    build_dir = project_dir / "build"
    command = [
        cmake_executable,
        "-S",
        str(project_dir),
        "-B",
        str(build_dir),
        *_probe_generator_args(),
    ]
    return command, subprocess.run(command, capture_output=True, text=True, check=False)


def _attempt_reflection(
    cmake_executable: str, work_dir: Path, script: str, *, cpp_std: int
) -> tuple[list[str], subprocess.CompletedProcess[str]]:
    """Try script mode, then a LANGUAGES NONE configure, then LANGUAGES CXX.

    Each attempt only runs if the previous one failed; see
    _reflect_functions_and_variables for why each tier exists.

    Args:
        cmake_executable: Absolute path to cmake.
        work_dir: Scratch directory for the throwaway script and project.
        script: The reflection script's complete text.
        cpp_std: The real project's C++ standard, for the last-resort
            LANGUAGES CXX retry.

    Returns:
        The last attempted command and its result.
    """
    command, completed = _run_script_mode(cmake_executable, work_dir, script)
    if completed.returncode != 0:
        command, completed = _run_reflection_configure(
            cmake_executable, work_dir, script, cpp_std=None
        )
    if completed.returncode != 0:
        command, completed = _run_reflection_configure(
            cmake_executable, work_dir, script, cpp_std=cpp_std
        )
    return command, completed


def _reflect_functions_and_variables(
    cmake_executable: str,
    *,
    work_dir: Path,
    reference: str,
    is_file: bool,
    module_path: Path | None,
    cpp_std: int,
) -> tuple[tuple[str, ...], tuple[str, ...], dict[str, str]]:
    """Run the required reflection pass: functions and variables.

    Tries, in order: CMake script mode (fast, no compiler needed); a
    throwaway LANGUAGES NONE configure, for commands script mode rejects as
    "not scriptable" (add_library(), add_executable(), ...) but that need
    no enabled language (INTERFACE libraries, custom targets, install
    rules); a throwaway LANGUAGES CXX configure with the real project's
    standard, for an include that declares an actual compiled target.
    Raises only if all three fail.

    Args:
        cmake_executable: Absolute path to cmake.
        work_dir: Scratch directory for the throwaway script and project.
        reference: An absolute file path or a bare module name.
        is_file: True when reference is a file path.
        module_path: An absolute CMAKE_MODULE_PATH entry to add, or None.
        cpp_std: The real project's C++ standard, for the last-resort
            LANGUAGES CXX retry.

    Returns:
        The newly-defined function names, variable names, and each
        variable's resolved value.

    Raises:
        CMakeError: When every attempt fails: reference does not exist, is
            not valid CMake, or (module case) is not found on the module
            path.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    output_path = work_dir / _OUTPUT_NAME
    include_statement = _include_statement(
        reference=reference, is_file=is_file, module_path=module_path
    )
    script = _reflection_script(output_path, include_statement)
    command, completed = _attempt_reflection(cmake_executable, work_dir, script, cpp_std=cpp_std)
    if completed.returncode != 0:
        raise CMakeError(
            f"Reflecting {reference!r} failed: cmake exited with code "
            f"{completed.returncode}. {completed.stderr.strip()} Check that "
            f"the path or module name is correct and that its CMake code "
            f"runs standalone (no assumptions about a parent project's "
            f"variables).",
            command=command,
            exit_code=completed.returncode,
        )
    return _parse_reflection_output(output_path)


def _parse_reflection_output(
    output_path: Path,
) -> tuple[tuple[str, ...], tuple[str, ...], dict[str, str]]:
    """Parse the plain, CMakeless-controlled output the reflection script wrote.

    This reads a fixed, tag-prefixed line format CMakeless's own wrapper
    script produces (see _reflect_functions_and_variables); it is not a
    CMake-language parser.

    Args:
        output_path: The file the reflection script wrote.

    Returns:
        The newly-defined function names, variable names, and each
        variable's resolved value.
    """
    functions: list[str] = []
    variables: list[str] = []
    values: dict[str, str] = {}
    pending_variable: str | None = None
    for line in output_path.read_text(encoding="utf-8").splitlines():
        if line.startswith(_FUNCTION_TAG):
            functions.append(line[len(_FUNCTION_TAG) :])
        elif line.startswith(_VARIABLE_TAG):
            name = line[len(_VARIABLE_TAG) :]
            pending_variable = None if name in _INTERNAL_VARIABLE_NAMES else name
            if pending_variable is not None:
                variables.append(pending_variable)
        elif line.startswith(_VALUE_TAG) and pending_variable is not None:
            values[pending_variable] = line[len(_VALUE_TAG) :]
            pending_variable = None
    return tuple(functions), tuple(variables), values


def _configure_target_probe(
    cmake_executable: str,
    probe_dir: Path,
    build_dir: Path,
    include_statement: str,
    *,
    cpp_std: int | None,
) -> subprocess.CompletedProcess[str]:
    """Configure one throwaway project for target discovery.

    Args:
        cmake_executable: Absolute path to cmake.
        probe_dir: The throwaway project's source directory.
        build_dir: The throwaway project's build directory.
        include_statement: The include() (and CMAKE_MODULE_PATH setup)
            under reflection.
        cpp_std: The C++ standard to configure CXX with, or None for a
            LANGUAGES NONE project (no compiler needed).

    Returns:
        The configure attempt's result.
    """
    (probe_dir / "CMakeLists.txt").write_text(
        _project_preamble(cpp_std) + include_statement + "\n", encoding="utf-8"
    )
    write_query(build_dir)
    command = [
        cmake_executable,
        "-S",
        str(probe_dir),
        "-B",
        str(build_dir),
        *_probe_generator_args(),
    ]
    return subprocess.run(command, capture_output=True, text=True, check=False)


def _reflect_targets(
    cmake_executable: str,
    *,
    work_dir: Path,
    reference: str,
    is_file: bool,
    module_path: Path | None,
    cpp_std: int,
) -> tuple[str, ...]:
    """Run the best-effort target-discovery pass: a throwaway configure.

    Tries LANGUAGES NONE first (fast, sidesteps compiler detection: most
    reflectable includes need no enabled language at all); an include that
    declares a real compiled target needs LANGUAGES CXX to configure, so a
    NONE failure retries once with the real project's C++ standard before
    giving up. Never raises: an include that only works inside its real
    parent project (assumed variables, missing dependencies) is expected to
    fail this minimal probe, so a failure here just means "targets
    unknown", not a problem worth surfacing.

    Args:
        cmake_executable: Absolute path to cmake.
        work_dir: Scratch directory for the throwaway project.
        reference: An absolute file path or a bare module name.
        is_file: True when reference is a file path.
        module_path: An absolute CMAKE_MODULE_PATH entry to add, or None.
        cpp_std: The real project's C++ standard.

    Returns:
        Target names the throwaway configure's codemodel reported, or an
        empty tuple when the probe could not configure.
    """
    probe_dir = work_dir / "tgt"
    build_dir = probe_dir / "build"
    try:
        probe_dir.mkdir(parents=True, exist_ok=True)
        include_statement = _include_statement(
            reference=reference, is_file=is_file, module_path=module_path
        )
        completed = _configure_target_probe(
            cmake_executable, probe_dir, build_dir, include_statement, cpp_std=None
        )
        if completed.returncode != 0:
            completed = _configure_target_probe(
                cmake_executable, probe_dir, build_dir, include_statement, cpp_std=cpp_std
            )
        if completed.returncode != 0:
            return ()
        return tuple(info.name for info in read_reply(build_dir))
    except OSError:
        return ()
