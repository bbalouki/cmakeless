"""The cmakeless command line: finds cmakelessfile.py and runs it.

The console script and 'python -m cmakeless' share this one implementation.
The build/configure/clean/lock verbs all execute the same cmakelessfile.py;
a verb override in the runtime context tells project.build() which step the
user asked for.
"""

from __future__ import annotations

import runpy
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated

import typer

from cmakeless._constants import BUILD_SCRIPT_NAME
from cmakeless._version import __version__
from cmakeless.api import _context
from cmakeless.driver.doctor import run_diagnostics
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

_STATUS_COLOURS = {
    "ok": typer.colors.GREEN,
    "FAIL": typer.colors.RED,
    "missing": typer.colors.YELLOW,
}

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
SanitizeOption = Annotated[
    str | None,
    typer.Option(
        "--sanitize",
        help='comma-separated sanitizers to test under, for example "address" '
        'or "address,undefined"; runs in its own build tree',
    ),
]
PrefixOption = Annotated[
    str | None,
    typer.Option("--prefix", help="installation prefix (default: CMake's platform default)"),
]
OfflineOption = Annotated[
    bool,
    typer.Option(
        "--offline",
        help="disallow network access; resolve only from cmakeless.lock, "
        "cmakeless.mirror.json, or an already-populated local cache",
    ),
]
SbomFormatOption = Annotated[
    str, typer.Option("--format", help='SBOM format: "cyclonedx" (the default) or "spdx"')
]
SbomOutputOption = Annotated[
    str | None,
    typer.Option(
        "--output", "-o", help="output file (default: <project name>.cdx.json/.spdx.json)"
    ),
]
VendorDirOption = Annotated[
    str | None,
    typer.Option("--directory", "-d", help="where to download archives (default: vendor/)"),
]


def main(argv: Sequence[str] | None = None) -> int:
    """Run the cmakeless command line.

    Args:
        argv: Arguments to parse; None reads sys.argv (console script use).

    Returns:
        The process exit code: 0 on success, 1 on any CmakelessError, 2 on a
        usage error.
    """
    command = typer.main.get_command(app)
    args = None if argv is None else list(argv)
    try:
        command.main(args=args, prog_name="cmakeless")
    except CmakelessError as error:
        typer.secho(f"cmakeless: error: {error}", fg=typer.colors.RED, err=True)
        return 1
    except SystemExit as exit_signal:
        return _exit_status(exit_signal)
    return 0


def _exit_status(exit_signal: SystemExit) -> int:
    """Turn the SystemExit the command layer raises into a process exit code.

    Args:
        exit_signal: The SystemExit raised once a command finished, whether it
            succeeded, printed help, or reported a usage error.

    Returns:
        The integer status; a None code means success, anything non-integer
        means failure, matching the interpreter's own convention.
    """
    code = exit_signal.code
    if code is None:
        return 0
    return code if isinstance(code, int) else 1


def _version_callback(requested: bool) -> None:
    """Print the version and stop, when --version was passed.

    Args:
        requested: True when the user passed --version.

    Raises:
        typer.Exit: Always, once the version has been printed.
    """
    if requested:
        typer.echo(f"cmakeless {__version__}")
        raise typer.Exit


@app.callback()
def _root(
    version: Annotated[
        bool,
        typer.Option(
            "--version", callback=_version_callback, is_eager=True, help="show the version and exit"
        ),
    ] = False,
) -> None:
    """Write your C++ builds in Python. Keep CMake. Lose the pain."""


@app.command()
def build(
    file: FileOption = BUILD_SCRIPT_NAME,
    generator: GeneratorOption = None,
    preset: PresetOption = None,
    offline: OfflineOption = False,
) -> None:
    """Run the project's cmakelessfile.py: freeze, emit, configure, and compile."""
    _run_verb("build", file=file, generator=generator, preset=preset, offline=offline)


@app.command()
def configure(
    file: FileOption = BUILD_SCRIPT_NAME,
    generator: GeneratorOption = None,
    preset: PresetOption = None,
    offline: OfflineOption = False,
) -> None:
    """Generate build files and run the CMake configure step only."""
    _run_verb("configure", file=file, generator=generator, preset=preset, offline=offline)


@app.command()
def test(
    file: FileOption = BUILD_SCRIPT_NAME,
    generator: GeneratorOption = None,
    preset: PresetOption = None,
    sanitize: SanitizeOption = None,
    offline: OfflineOption = False,
) -> None:
    """Build everything, then run the test suite through CTest."""
    _run_verb(
        "test", file=file, generator=generator, preset=preset, sanitize=sanitize, offline=offline
    )


@app.command()
def install(
    file: FileOption = BUILD_SCRIPT_NAME,
    generator: GeneratorOption = None,
    preset: PresetOption = None,
    prefix: PrefixOption = None,
    offline: OfflineOption = False,
) -> None:
    """Build everything, then install it through cmake --install."""
    _run_verb(
        "install", file=file, generator=generator, preset=preset, prefix=prefix, offline=offline
    )


@app.command()
def package(
    file: FileOption = BUILD_SCRIPT_NAME,
    generator: GeneratorOption = None,
    preset: PresetOption = None,
    offline: OfflineOption = False,
) -> None:
    """Build everything, then produce packages through CPack."""
    _run_verb("package", file=file, generator=generator, preset=preset, offline=offline)


@app.command()
def clean(file: FileOption = BUILD_SCRIPT_NAME) -> None:
    """Delete the project's build directory."""
    _run_verb("clean", file=file)


@app.command()
def lock(file: FileOption = BUILD_SCRIPT_NAME, offline: OfflineOption = False) -> None:
    """Resolve dependencies and refresh cmakeless.lock."""
    _run_verb("lock", file=file, offline=offline)


@app.command()
def options(file: FileOption = BUILD_SCRIPT_NAME) -> None:
    """List this project's declared options without building anything."""
    _run_verb("options", file=file)


@app.command()
def sbom(
    file: FileOption = BUILD_SCRIPT_NAME,
    output_format: SbomFormatOption = "cyclonedx",
    output: SbomOutputOption = None,
) -> None:
    """Generate a CycloneDX or SPDX bill of materials from cmakeless.lock."""
    _run_verb("sbom", file=file, sbom_format=output_format, sbom_output=output)


@app.command()
def vendor(file: FileOption = BUILD_SCRIPT_NAME, directory: VendorDirOption = None) -> None:
    """Download every locked dependency into vendor/ for offline builds."""
    _run_verb("vendor", file=file, vendor_directory=directory)


@app.command()
def init(
    name: Annotated[
        str | None,
        typer.Option("--name", help="project name (default: the current directory's name)"),
    ] = None,
) -> None:
    """Scaffold a new project: cmakelessfile.py, src/main.cpp, and .gitignore."""
    _init_project(Path.cwd(), name=name)


@app.command()
def doctor() -> None:
    """Check cmake, the generator, ccache/vcpkg/Conan, and network access.

    Raises:
        typer.Exit: With code 1 when a required check failed.
    """
    if not _print_doctor_report():
        raise typer.Exit(code=1)


def _run_verb(
    verb: str,
    *,
    file: str,
    generator: str | None = None,
    preset: str | None = None,
    sanitize: str | None = None,
    prefix: str | None = None,
    offline: bool = False,
    sbom_format: str = "cyclonedx",
    sbom_output: str | None = None,
    vendor_directory: str | None = None,
) -> None:
    """Execute a cmakelessfile.py verb with the CLI's overrides active.

    Each verb passes only the options it accepts; the rest keep the defaults
    the runtime context expects when a flag does not apply to that verb.

    Args:
        verb: The subcommand name, which project.build() reads back.
        file: Path to the build description to execute.
        generator: The --generator value, when the verb accepts one.
        preset: The --preset value, when the verb accepts one.
        sanitize: The raw --sanitize value, when the verb accepts one.
        prefix: The --prefix value, when the verb accepts one.
        offline: The --offline flag, when the verb accepts it.
        sbom_format: The --format value of the sbom verb.
        sbom_output: The --output value of the sbom verb.
        vendor_directory: The --directory value of the vendor verb.

    Raises:
        CmakelessError: Whatever the build description or pipeline raises.
    """
    with (
        _context.verb_override(verb),
        _context.generator_override(generator),
        _context.preset_override(preset),
        _context.sanitize_override(_parse_sanitize(sanitize)),
        _context.prefix_override(prefix),
        _context.offline_override(offline),
        _context.sbom_format_override(sbom_format),
        _context.sbom_output_override(sbom_output),
        _context.vendor_directory_override(vendor_directory),
    ):
        _run_build_script(Path(file))


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


def _print_doctor_report() -> bool:
    """Run and print the 'doctor' verb's environment diagnostics.

    Returns:
        True when every required check passed, driving main()'s exit code.
    """
    checks = run_diagnostics()
    typer.echo("[cmakeless] doctor")
    for check in checks:
        status = "ok" if check.ok else ("FAIL" if check.required else "missing")
        # Pad before styling so the colour codes never count toward the column
        # width, and so stripping them on a non-terminal leaves the table aligned.
        coloured = typer.style(f"{status:<6}", fg=_STATUS_COLOURS[status])
        typer.echo(f"  {check.name:<10} {coloured} {check.detail}")
    return all(check.ok for check in checks if check.required)


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
    typer.secho(
        f"[cmakeless] Scaffolded project {project_name!r} in {directory}",
        fg=typer.colors.GREEN,
    )
    typer.echo(
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
