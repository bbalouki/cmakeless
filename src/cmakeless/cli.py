"""The cmakeless command line: finds build.py and runs it.

The console script and 'python -m cmakeless' share this one implementation.
The build/configure/clean verbs all execute the same build.py; a verb override
in the runtime context tells project.build() which step the user asked for.
"""

from __future__ import annotations

import argparse
import runpy
import sys
from collections.abc import Sequence
from pathlib import Path

from cmakeless._version import __version__
from cmakeless.api import _context
from cmakeless.errors import CmakelessError, ConfigurationError

BUILD_SCRIPT_NAME = "build.py"

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
__pycache__/
"""


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            _init_project(Path.cwd(), name=args.name)
        else:
            generator = getattr(args, "generator", None)
            with _context.verb_override(args.command), _context.generator_override(generator):
                _run_build_script(Path(args.file))
    except CmakelessError as error:
        print(f"cmakeless: error: {error}", file=sys.stderr)
        return 1
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cmakeless",
        description="Write your C++ builds in Python. Keep CMake. Lose the pain.",
    )
    parser.add_argument("--version", action="version", version=f"cmakeless {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    help_by_verb = {
        "build": "run the project's build.py (freeze, emit, configure, compile)",
        "configure": "generate build files and run the CMake configure step only",
        "clean": "delete the project's build directory",
    }
    for verb, help_text in help_by_verb.items():
        verb_parser = subparsers.add_parser(verb, help=help_text)
        verb_parser.add_argument(
            "--file",
            default=BUILD_SCRIPT_NAME,
            help=f"path to the build description (default: {BUILD_SCRIPT_NAME})",
        )
        if verb != "clean":
            verb_parser.add_argument(
                "--generator",
                default=None,
                help='CMake generator: "ninja", "vs", or any raw -G name '
                "(default: ninja when available)",
            )

    init_parser = subparsers.add_parser(
        "init", help="scaffold a new project (build.py, src/main.cpp, .gitignore)"
    )
    init_parser.add_argument(
        "--name",
        default=None,
        help="project name (default: the current directory's name)",
    )
    return parser


def _run_build_script(script: Path) -> None:
    if not script.is_file():
        raise ConfigurationError(
            f"No build description found at '{script}'. Run cmakeless from the "
            f"directory containing {BUILD_SCRIPT_NAME}, or point at one with "
            f"--file path/to/{BUILD_SCRIPT_NAME}."
        )
    # The script is the tool: running it under __main__ makes 'cmakeless build'
    # behave exactly like 'python build.py'.
    runpy.run_path(str(script), run_name="__main__")


def _init_project(directory: Path, *, name: str | None) -> None:
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
        "[cmakeless] Next: run 'cmakeless build' (or 'python build.py'), then "
        "./build/" + project_name
    )


def _sanitize_name(raw: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "_.+-" else "_" for ch in raw)
    if not cleaned or not (cleaned[0].isalpha() or cleaned[0] == "_"):
        cleaned = f"project_{cleaned}" if cleaned else "my_project"
    return cleaned
