# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""The cmakeless command line: finds cmakelessfile.py and runs it.

The console script and 'python -m cmakeless' share this one implementation.
The build/configure/clean/lock verbs all execute the same cmakelessfile.py;
a verb override in the runtime context tells project.build() which step the
user asked for.
"""

from __future__ import annotations

import argparse
import runpy
import sys
from collections.abc import Sequence
from pathlib import Path

from cmakeless._constants import BUILD_SCRIPT_NAME
from cmakeless._version import __version__
from cmakeless.api import _context
from cmakeless.errors import CmakelessError, ConfigurationError

_INIT_BUILD_PY = """\
from cmakeless import Project

project = Project("{name}", version="0.1.0", cpp_std=20)
project.add_executable("{name}", sources=["src/main.cpp"])
project.build()
"""

_INIT_MAIN_CPP = """\
#include <cstdlib>
#include <iostream>

auto main() -> int
{
    std::cout << "Hello from cmakeless!\\n";
    return EXIT_SUCCESS;
}
"""

_INIT_GITIGNORE = """\
build/
CMakeLists.txt
CMakePresets.json
compile_commands.json
__pycache__/
"""


def main(argv: Sequence[str] | None = None) -> int:
    """Run the cmakeless command line.

    Args:
        argv: Arguments to parse; None reads sys.argv (console script use).

    Returns:
        The process exit code: 0 on success, 1 on any CmakelessError.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            _init_project(Path.cwd(), name=args.name)
        else:
            _run_verb(args)
    except CmakelessError as error:
        print(f"cmakeless: error: {error}", file=sys.stderr)
        return 1
    return 0


def _run_verb(args: argparse.Namespace) -> None:
    """Execute a cmakelessfile.py verb with the CLI's overrides active.

    Args:
        args: The parsed arguments of one script verb.

    Raises:
        CmakelessError: Whatever the build description or pipeline raises.
    """
    generator = getattr(args, "generator", None)
    preset = getattr(args, "preset", None)
    sanitize = _parse_sanitize(getattr(args, "sanitize", None))
    prefix = getattr(args, "prefix", None)
    with (
        _context.verb_override(args.command),
        _context.generator_override(generator),
        _context.preset_override(preset),
        _context.sanitize_override(sanitize),
        _context.prefix_override(prefix),
    ):
        _run_build_script(Path(args.file))


def _parse_sanitize(raw: str | None) -> tuple[str, ...]:
    """Split the --sanitize argument into sanitizer names.

    Args:
        raw: The comma-separated value, or None when not given.

    Returns:
        The names, stripped and empties dropped; validation happens at
        freeze time where the error message has full context.
    """
    if raw is None:
        return ()
    return tuple(name.strip() for name in raw.split(",") if name.strip())


def _build_parser() -> argparse.ArgumentParser:
    """Assemble the argument parser with every subcommand.

    Returns:
        The configured top-level parser.
    """
    parser = argparse.ArgumentParser(
        prog="cmakeless",
        description="Write your C++ builds in Python. Keep CMake. Lose the pain.",
    )
    parser.add_argument("--version", action="version", version=f"cmakeless {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)
    _add_script_verbs(subparsers)
    init_parser = subparsers.add_parser(
        "init", help="scaffold a new project (cmakelessfile.py, src/main.cpp, .gitignore)"
    )
    init_parser.add_argument(
        "--name",
        default=None,
        help="project name (default: the current directory's name)",
    )
    return parser


def _add_script_verbs(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the verbs that execute the project's cmakelessfile.py.

    Args:
        subparsers: The subcommand registry of the top-level parser.
    """
    help_by_verb = {
        "build": "run the project's cmakelessfile.py (freeze, emit, configure, compile)",
        "configure": "generate build files and run the CMake configure step only",
        "test": "build everything, then run the test suite through CTest",
        "install": "build everything, then install it through cmake --install",
        "package": "build everything, then produce packages through CPack",
        "clean": "delete the project's build directory",
        "lock": "resolve dependencies and refresh cmakeless.lock",
        "options": "list this project's declared options without building anything",
    }
    for verb, help_text in help_by_verb.items():
        _add_verb_options(subparsers.add_parser(verb, help=help_text), verb)


def _add_verb_options(verb_parser: argparse.ArgumentParser, verb: str) -> None:
    """Register the options one script verb accepts.

    Args:
        verb_parser: The verb's own subparser.
        verb: The verb name, deciding which options apply.
    """
    verb_parser.add_argument(
        "--file",
        default=BUILD_SCRIPT_NAME,
        help=f"path to the build description (default: {BUILD_SCRIPT_NAME})",
    )
    if verb not in ("clean", "lock", "options"):
        verb_parser.add_argument(
            "--generator",
            default=None,
            help='CMake generator: "ninja", "ninja-multi", "make", "vs", "xcode", '
            "or any raw -G name (default: ninja when available)",
        )
        verb_parser.add_argument(
            "--preset",
            default=None,
            help="configure and build with this preset from CMakePresets.json",
        )
    if verb == "test":
        verb_parser.add_argument(
            "--sanitize",
            default=None,
            help='comma-separated sanitizers to test under, for example "address" '
            'or "address,undefined"; runs in its own build tree',
        )
    if verb == "install":
        verb_parser.add_argument(
            "--prefix",
            default=None,
            help="installation prefix (default: CMake's platform default)",
        )


def _run_build_script(script: Path) -> None:
    """Execute the user's build description as if run directly.

    The script is the tool: running it under __main__ makes 'cmakeless
    build' behave exactly like 'python cmakelessfile.py'.

    Args:
        script: Path of the build description to execute.

    Raises:
        ConfigurationError: When the script does not exist.
    """
    if not script.is_file():
        raise ConfigurationError(
            f"No build description found at '{script}'. Run cmakeless from the "
            f"directory containing {BUILD_SCRIPT_NAME}, or point at one with "
            f"--file path/to/{BUILD_SCRIPT_NAME}."
        )
    runpy.run_path(str(script), run_name="__main__")


def _init_project(directory: Path, *, name: str | None) -> None:
    """Scaffold a new project in the given directory.

    Writes cmakelessfile.py, src/main.cpp, and .gitignore, refusing to
    overwrite an existing cmakelessfile.py and leaving other existing files
    untouched.

    Args:
        directory: Where to scaffold (the CLI passes the working directory).
        name: The project name; None derives it from the directory name.

    Raises:
        ConfigurationError: When a cmakelessfile.py already exists there.
    """
    project_name = name if name is not None else _sanitize_name(directory.name)
    script = directory / BUILD_SCRIPT_NAME
    if script.exists():
        raise ConfigurationError(
            f"A {BUILD_SCRIPT_NAME} already exists in {directory}; refusing to "
            f"overwrite it. Delete it first if you really want to start over."
        )
    (directory / "src").mkdir(exist_ok=True)
    script.write_text(_INIT_BUILD_PY.format(name=project_name), encoding="utf-8", newline="\n")
    main_cpp = directory / "src" / "main.cpp"
    if not main_cpp.exists():
        main_cpp.write_text(_INIT_MAIN_CPP, encoding="utf-8", newline="\n")
    gitignore = directory / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(_INIT_GITIGNORE, encoding="utf-8", newline="\n")
    print(f"[cmakeless] Scaffolded project {project_name!r} in {directory}")
    print(
        "[cmakeless] Next: run 'cmakeless build' (or 'python cmakelessfile.py'), then "
        "./build/" + project_name
    )


def _sanitize_name(raw: str) -> str:
    """Derive a valid project name from a directory name.

    Args:
        raw: The directory name, which may contain anything.

    Returns:
        A name that passes project-name validation.
    """
    cleaned = "".join(ch if ch.isalnum() or ch in "_.+-" else "_" for ch in raw)
    if not cleaned or not (cleaned[0].isalpha() or cleaned[0] == "_"):
        cleaned = f"project_{cleaned}" if cleaned else "my_project"
    return cleaned
