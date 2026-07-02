"""The cmakeless command line: finds build.py and runs it.

The console script and 'python -m cmakeless' share this one implementation.
"""

from __future__ import annotations

import argparse
import runpy
import sys
from collections.abc import Sequence
from pathlib import Path

from cmakeless._version import __version__
from cmakeless.errors import CmakelessError, ConfigurationError

BUILD_SCRIPT_NAME = "build.py"


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
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

    build_parser = subparsers.add_parser(
        "build", help="run the project's build.py (freeze, emit, configure, compile)"
    )
    build_parser.add_argument(
        "--file",
        default=BUILD_SCRIPT_NAME,
        help=f"path to the build description (default: {BUILD_SCRIPT_NAME})",
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
