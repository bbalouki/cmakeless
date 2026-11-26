"""Shared pieces of the command line: the Typer app, option types, and the verb runner."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Annotated

import typer

from cmakeless._constants import BUILD_SCRIPT_NAME
from cmakeless.api import _context
from cmakeless.api.workspace import WORKSPACE_SCRIPT_NAME
from cmakeless.errors import ConfigurationError

# Rich markup and pretty tracebacks stay off: this CLI's output is plain text
# that scripts and CI logs read line by line, so help and errors go through the
# plain formatter rather than a terminal-width-sensitive renderer.
app = typer.Typer(
    name="cmakeless",
    help="Write your C++ builds in Python. Keep CMake. Lose the pain.",
    rich_markup_mode=None,
    pretty_exceptions_enable=False,
    no_args_is_help=True,
)

FileOption = Annotated[
    str,
    typer.Option("--file", help=f"path to the build description (default: {BUILD_SCRIPT_NAME})"),
]
GeneratorOption = Annotated[
    str | None,
    typer.Option(
        "--generator",
        help='CMake generator: "ninja", "ninja-multi", "make", "vs", "xcode", '
        "or any raw -G name (default: ninja when available)",
    ),
]
PresetOption = Annotated[
    str | None,
    typer.Option("--preset", help="configure and build with this preset from CMakePresets.json"),
]
OfflineOption = Annotated[
    bool,
    typer.Option(
        "--offline",
        help="disallow network access; resolve only from cmakeless.lock, "
        "cmakeless.mirror.json, or an already-populated local cache",
    ),
]
TargetOption = Annotated[str | None, typer.Option("--target", help="build only this target")]
JobsOption = Annotated[
    int | None, typer.Option("--jobs", "-j", min=1, help="parallel jobs (default: the tool's own)")
]
ConfigOption = Annotated[
    str | None,
    typer.Option("--config", help="configuration for multi-config generators, e.g. Release"),
]
VerboseOption = Annotated[
    bool, typer.Option("--verbose", "-v", help="show the real compiler and linker command lines")
]
FreshOption = Annotated[bool, typer.Option("--fresh", help="discard the CMake cache first")]
DefineOption = Annotated[
    list[str] | None,
    typer.Option("--define", "-D", help="set a cache variable, NAME=VALUE (repeatable)"),
]
JsonOption = Annotated[
    bool, typer.Option("--json", help="stream progress events as JSON lines (for tools)")
]
ProjectOption = Annotated[
    str | None, typer.Option("--project", help="in a workspace: run only this member")
]
AffectedOption = Annotated[
    str | None,
    typer.Option("--affected-since", help="in a workspace: only members changed since a git ref"),
]


def parse_defines(raw: list[str] | None) -> tuple[tuple[str, str], ...]:
    """Split -D NAME=VALUE arguments.

    Args:
        raw: The repeated --define values.

    Returns:
        (name, value) pairs, in order.

    Raises:
        ConfigurationError: When an entry has no '=' or no name.
    """
    pairs = []
    for entry in raw or []:
        name, separator, value = entry.partition("=")
        if not separator or not name:
            raise ConfigurationError(f"-D {entry!r} must look like NAME=VALUE.")
        pairs.append((name, value))
    return tuple(pairs)


def run_script_verb(
    verb: str,
    *,
    file: str,
    options: _context.RunOptions | None = None,
    generator: str | None = None,
    preset: str | None = None,
    offline: bool = False,
) -> None:
    """Execute a build description (or workspace) with one verb active.

    Args:
        verb: The subcommand name, which project.build() reads back.
        file: Path to the build description.
        options: The run options for this verb, or None for the defaults.
        generator: The --generator value.
        preset: The --preset value.
        offline: The --offline flag.

    Raises:
        CmakelessError: Whatever the build description or pipeline raises.
    """
    with (
        _context.verb_override(verb),
        _context.generator_override(generator),
        _context.preset_override(preset),
        _context.offline_override(offline),
        _context.run_options_override(options or _context.RunOptions()),
    ):
        run_build_script(_resolve_script(Path(file)))


def _resolve_script(script: Path) -> Path:
    """Fall back to a workspace description when no project description exists.

    Args:
        script: The --file value.

    Returns:
        The build description, or cmakelessworkspace.py next to it.
    """
    workspace = script.with_name(WORKSPACE_SCRIPT_NAME)
    if script.name == BUILD_SCRIPT_NAME and not script.is_file() and workspace.is_file():
        return workspace
    return script


def run_build_script(script: Path) -> None:
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
            f"directory containing {BUILD_SCRIPT_NAME} (or {WORKSPACE_SCRIPT_NAME}), "
            f"or point at one with --file path/to/{BUILD_SCRIPT_NAME}."
        )
    runpy.run_path(str(script), run_name="__main__")
