"""The cmakeless command line: finds cmakelessfile.py and runs it.

The console script and 'python -m cmakeless' share this one implementation.
Every script verb executes the same cmakelessfile.py; a verb override in the
runtime context tells project.build() which step the user asked for.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Annotated

import typer

from cmakeless._cli import workflows as _cli_workflows
from cmakeless._cli.common import (
    AffectedOption,
    ConfigOption,
    DefineOption,
    FileOption,
    FreshOption,
    GeneratorOption,
    JobsOption,
    JsonOption,
    OfflineOption,
    PresetOption,
    ProjectOption,
    TargetOption,
    VerboseOption,
    app,
    parse_defines,
    run_script_verb,
)
from cmakeless._constants import BUILD_SCRIPT_NAME
from cmakeless._version import __version__
from cmakeless.api import _context
from cmakeless.driver.doctor import run_diagnostics
from cmakeless.errors import CmakelessError, ConfigurationError
from cmakeless.tools.templates import available_templates, render_template, write_template

_STATUS_COLOURS = {
    "ok": typer.colors.GREEN,
    "FAIL": typer.colors.RED,
    "missing": typer.colors.YELLOW,
}

# The workflow verbs register themselves on the shared app when imported.
WORKFLOW_COMMANDS = _cli_workflows.COMMANDS

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
FilterOption = Annotated[
    str | None, typer.Option("--filter", "-R", help="run only tests matching this regex")
]
LabelOption = Annotated[str | None, typer.Option("--label", "-L", help="run only tests with label")]
RepeatOption = Annotated[
    int | None, typer.Option("--repeat", min=1, help="rerun each test until it fails, N times")
]
JunitOption = Annotated[str | None, typer.Option("--junit", help="write a JUnit XML report here")]


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


def _build_run_options(
    *,
    target: str | None,
    jobs: int | None,
    config: str | None,
    verbose: bool,
    fresh: bool,
    define: list[str] | None,
    json_events: bool,
    project: str | None,
    affected_since: str | None,
) -> _context.RunOptions:
    """Collect the flags every build-like verb shares.

    Args:
        target: --target.
        jobs: --jobs.
        config: --config.
        verbose: --verbose.
        fresh: --fresh.
        define: The repeated --define values.
        json_events: --json.
        project: --project (workspaces).
        affected_since: --affected-since (workspaces).

    Returns:
        The run options.
    """
    return _context.RunOptions(
        target=target,
        jobs=jobs,
        config=config,
        verbose=verbose,
        fresh=fresh,
        defines=parse_defines(define),
        json_events=json_events,
        workspace_project=project,
        affected_since=affected_since,
    )


@app.command()
def build(
    file: FileOption = BUILD_SCRIPT_NAME,
    generator: GeneratorOption = None,
    preset: PresetOption = None,
    offline: OfflineOption = False,
    target: TargetOption = None,
    jobs: JobsOption = None,
    config: ConfigOption = None,
    verbose: VerboseOption = False,
    fresh: FreshOption = False,
    define: DefineOption = None,
    json_events: JsonOption = False,
    project: ProjectOption = None,
    affected_since: AffectedOption = None,
) -> None:
    """Run the project's cmakelessfile.py: freeze, emit, configure, and compile."""
    options = _build_run_options(
        target=target,
        jobs=jobs,
        config=config,
        verbose=verbose,
        fresh=fresh,
        define=define,
        json_events=json_events,
        project=project,
        affected_since=affected_since,
    )
    run_script_verb(
        "build", file=file, options=options, generator=generator, preset=preset, offline=offline
    )


@app.command()
def configure(
    file: FileOption = BUILD_SCRIPT_NAME,
    generator: GeneratorOption = None,
    preset: PresetOption = None,
    offline: OfflineOption = False,
    fresh: FreshOption = False,
    define: DefineOption = None,
    json_events: JsonOption = False,
    project: ProjectOption = None,
) -> None:
    """Generate build files and run the CMake configure step only."""
    options = _context.RunOptions(
        fresh=fresh,
        defines=parse_defines(define),
        json_events=json_events,
        workspace_project=project,
    )
    run_script_verb(
        "configure", file=file, options=options, generator=generator, preset=preset, offline=offline
    )


@app.command()
def test(
    file: FileOption = BUILD_SCRIPT_NAME,
    generator: GeneratorOption = None,
    preset: PresetOption = None,
    sanitize: SanitizeOption = None,
    offline: OfflineOption = False,
    jobs: JobsOption = None,
    config: ConfigOption = None,
    test_filter: FilterOption = None,
    label: LabelOption = None,
    repeat: RepeatOption = None,
    junit: JunitOption = None,
    json_events: JsonOption = False,
    project: ProjectOption = None,
    affected_since: AffectedOption = None,
) -> None:
    """Build everything, then run the test suite through CTest."""
    options = _context.RunOptions(
        jobs=jobs,
        config=config,
        test_filter=test_filter,
        test_label=label,
        test_repeat=repeat,
        junit=junit,
        json_events=json_events,
        workspace_project=project,
        affected_since=affected_since,
    )
    with _context.sanitize_override(_parse_sanitize(sanitize)):
        run_script_verb(
            "test", file=file, options=options, generator=generator, preset=preset, offline=offline
        )


@app.command()
def install(
    file: FileOption = BUILD_SCRIPT_NAME,
    generator: GeneratorOption = None,
    preset: PresetOption = None,
    prefix: PrefixOption = None,
    offline: OfflineOption = False,
    config: ConfigOption = None,
) -> None:
    """Build everything, then install it through cmake --install."""
    options = _context.RunOptions(config=config)
    with _context.prefix_override(prefix):
        run_script_verb(
            "install",
            file=file,
            options=options,
            generator=generator,
            preset=preset,
            offline=offline,
        )


@app.command()
def package(
    file: FileOption = BUILD_SCRIPT_NAME,
    generator: GeneratorOption = None,
    preset: PresetOption = None,
    offline: OfflineOption = False,
) -> None:
    """Build everything, then produce packages through CPack."""
    run_script_verb("package", file=file, generator=generator, preset=preset, offline=offline)


@app.command()
def clean(file: FileOption = BUILD_SCRIPT_NAME) -> None:
    """Delete the project's build directory."""
    run_script_verb("clean", file=file)


@app.command()
def lock(
    file: FileOption = BUILD_SCRIPT_NAME,
    offline: OfflineOption = False,
    package_names: Annotated[
        list[str] | None,
        typer.Option("--package", "-p", help="refresh only this package (repeatable)"),
    ] = None,
) -> None:
    """Resolve dependencies and refresh cmakeless.lock."""
    options = _context.RunOptions(lock_packages=tuple(package_names or ()))
    run_script_verb("lock", file=file, options=options, offline=offline)


@app.command()
def options(file: FileOption = BUILD_SCRIPT_NAME) -> None:
    """List this project's declared options without building anything."""
    run_script_verb("options", file=file)


@app.command()
def sbom(
    file: FileOption = BUILD_SCRIPT_NAME,
    output_format: SbomFormatOption = "cyclonedx",
    output: SbomOutputOption = None,
) -> None:
    """Generate a reproducible CycloneDX or SPDX bill of materials from cmakeless.lock."""
    with _context.sbom_format_override(output_format), _context.sbom_output_override(output):
        run_script_verb("sbom", file=file)


@app.command()
def vendor(file: FileOption = BUILD_SCRIPT_NAME, directory: VendorDirOption = None) -> None:
    """Download every locked dependency into vendor/ for offline builds."""
    with _context.vendor_directory_override(directory):
        run_script_verb("vendor", file=file)


@app.command()
def init(
    name: Annotated[
        str | None,
        typer.Option("--name", help="project name (default: the current directory's name)"),
    ] = None,
    template: Annotated[
        str,
        typer.Option(
            "--template", "-t", help="app, library, game, embedded, python-ext, low-latency"
        ),
    ] = "app",
    list_templates: Annotated[
        bool, typer.Option("--list", help="list the available templates and exit")
    ] = False,
) -> None:
    """Scaffold a new project from a template, CI and editor settings included."""
    if list_templates:
        for template_name, origin in sorted(available_templates().items()):
            typer.echo(f"  {template_name:<14} {origin}")
        return
    _init_project(Path.cwd(), name=name, template=template)


@app.command()
def doctor() -> None:
    """Check cmake, the generator, compilers, caches, package managers, and network.

    Raises:
        typer.Exit: With code 1 when a required check failed.
    """
    if not _print_doctor_report():
        raise typer.Exit(code=1)


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


def _init_project(directory: Path, *, name: str | None, template: str = "app") -> None:
    """Scaffold a new project in the given directory from a template.

    Refuses to overwrite an existing cmakelessfile.py and leaves every other
    existing file untouched.

    Args:
        directory: Where to scaffold (the CLI passes the working directory).
        name: The project name; None derives it from the directory name.
        template: The template name.

    Raises:
        ConfigurationError: When a cmakelessfile.py already exists there, or
            the template is unknown.
    """
    project_name = name if name is not None else _sanitize_name(directory.name)
    if (directory / BUILD_SCRIPT_NAME).exists():
        raise ConfigurationError(
            f"A {BUILD_SCRIPT_NAME} already exists in {directory}; refusing to "
            f"overwrite it. Delete it first if you really want to start over."
        )
    written = write_template(directory, render_template(template, project_name))
    typer.secho(
        f"[cmakeless] Scaffolded {template} project {project_name!r} in {directory} "
        f"({len(written)} files)",
        fg=typer.colors.GREEN,
    )
    typer.echo("[cmakeless] Next: run 'cmakeless build', then 'cmakeless test'.")


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
