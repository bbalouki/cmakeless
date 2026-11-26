"""The workflow verbs: run, explain, diff, audit, quality, evidence, import, search.

Importing this module registers every verb on the shared Typer app.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from cmakeless._cli.common import (
    ConfigOption,
    FileOption,
    GeneratorOption,
    JobsOption,
    OfflineOption,
    PresetOption,
    app,
    run_script_verb,
)
from cmakeless._constants import BUILD_SCRIPT_NAME
from cmakeless.api import _context
from cmakeless.deps.registry import known_packages, registry_entry
from cmakeless.errors import ConfigurationError
from cmakeless.tools.importer import check_import, import_project

OutputOption = Annotated[
    str | None, typer.Option("--output", "-o", help="where to write the result")
]
ExitCodeOption = Annotated[
    bool, typer.Option("--exit-code", help="exit 1 when anything is found, for CI gates")
]

COMMANDS = (
    "run",
    "explain",
    "diff",
    "audit",
    "matrix",
    "coverage",
    "fuzz",
    "pgo",
    "profile",
    "lint",
    "evidence",
    "verify",
    "import",
    "search",
)


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def run(
    ctx: typer.Context,
    target: Annotated[str, typer.Argument(help="the executable to build and run")],
    file: FileOption = BUILD_SCRIPT_NAME,
    preset: PresetOption = None,
    jobs: JobsOption = None,
) -> None:
    """Build one executable and run it; arguments after '--' go to the program."""
    options = _context.RunOptions(target=target, jobs=jobs, program_args=tuple(ctx.args))
    run_script_verb("run", file=file, options=options, preset=preset)


@app.command()
def explain(
    subject: Annotated[str, typer.Argument(help="a target name, or cmakelessfile.py:LINE")],
    file: FileOption = BUILD_SCRIPT_NAME,
) -> None:
    """Show where a target was declared and exactly the CMake it produced."""
    run_script_verb("explain", file=file, options=_context.RunOptions(subject=subject))


@app.command()
def diff(file: FileOption = BUILD_SCRIPT_NAME, exit_code: ExitCodeOption = False) -> None:
    """Show how the build files on disk differ from what would be generated."""
    run_script_verb("diff", file=file, options=_context.RunOptions(exit_code=exit_code))


@app.command()
def audit(
    file: FileOption = BUILD_SCRIPT_NAME,
    approve: Annotated[
        list[str] | None,
        typer.Option("--approve", help="mark a reviewed trust-on-first-use pin (repeatable)"),
    ] = None,
    exit_code: ExitCodeOption = False,
) -> None:
    """Report how every locked dependency pin was obtained, and what needs review."""
    options = _context.RunOptions(approve=tuple(approve or ()), exit_code=exit_code)
    run_script_verb("audit", file=file, options=options)


@app.command()
def matrix(
    file: FileOption = BUILD_SCRIPT_NAME,
    presets: Annotated[
        str | None, typer.Option("--presets", help="comma-separated presets (default: all)")
    ] = None,
    json_report: Annotated[bool, typer.Option("--json", help="print the summary as JSON")] = False,
    generator: GeneratorOption = None,
) -> None:
    """Configure, build, and test several presets, then summarize them."""
    names = tuple(name.strip() for name in (presets or "").split(",") if name.strip())
    options = _context.RunOptions(presets=names, report="json" if json_report else "text")
    run_script_verb("matrix", file=file, options=options, generator=generator)


@app.command()
def coverage(file: FileOption = BUILD_SCRIPT_NAME, jobs: JobsOption = None) -> None:
    """Build an instrumented tree, run the tests, and write an HTML and Cobertura report."""
    run_script_verb("coverage", file=file, options=_context.RunOptions(jobs=jobs))


@app.command()
def fuzz(
    target: Annotated[str, typer.Argument(help="a target from project.add_fuzz_target()")],
    file: FileOption = BUILD_SCRIPT_NAME,
    seconds: Annotated[int, typer.Option("--time", min=1, help="how long to fuzz")] = 60,
) -> None:
    """Build a libFuzzer target and run it against its corpus for a fixed time."""
    options = _context.RunOptions(subject=target, fuzz_seconds=seconds)
    run_script_verb("fuzz", file=file, options=options)


@app.command()
def pgo(
    train: Annotated[str, typer.Option("--train", help="the training command line to run")],
    file: FileOption = BUILD_SCRIPT_NAME,
    jobs: JobsOption = None,
) -> None:
    """Instrument, train, merge profiles, and rebuild with profile-guided optimization."""
    run_script_verb("pgo", file=file, options=_context.RunOptions(train=train, jobs=jobs))


@app.command()
def profile(file: FileOption = BUILD_SCRIPT_NAME, jobs: JobsOption = None) -> None:
    """Rebuild with timing on and report the slowest steps and most expensive headers."""
    run_script_verb("profile", file=file, options=_context.RunOptions(jobs=jobs))


@app.command()
def lint(
    file: FileOption = BUILD_SCRIPT_NAME,
    report: Annotated[str, typer.Option("--report", help='"text" or "sarif"')] = "text",
    output: OutputOption = None,
    exit_code: ExitCodeOption = False,
) -> None:
    """Run clang-tidy over every project source; SARIF feeds GitHub code scanning."""
    if report not in ("text", "sarif"):
        raise ConfigurationError(f'--report {report!r} must be "text" or "sarif".')
    options = _context.RunOptions(report=report, output=output, exit_code=exit_code)
    run_script_verb("lint", file=file, options=options)


@app.command()
def evidence(
    file: FileOption = BUILD_SCRIPT_NAME,
    preset: PresetOption = None,
    output: OutputOption = None,
    config: ConfigOption = None,
    offline: OfflineOption = False,
) -> None:
    """Build, test, and write an auditable bundle: manifest, toolchain, SBOM, provenance."""
    options = _context.RunOptions(output=output, config=config)
    run_script_verb("evidence", file=file, options=options, preset=preset, offline=offline)


@app.command()
def verify(file: FileOption = BUILD_SCRIPT_NAME, offline: OfflineOption = False) -> None:
    """Build twice in separate trees and check the outputs are bit-identical."""
    run_script_verb("verify", file=file, offline=offline)


@app.command("import")
def import_cmake(
    source: Annotated[Path, typer.Option("--source", help="the CMake project root")] = Path(),
    check: Annotated[
        bool, typer.Option("--check", help="prove the conversion builds the same targets")
    ] = False,
    force: Annotated[bool, typer.Option("--force", help="overwrite cmakelessfile.py")] = False,
) -> None:
    """Convert an existing CMakeLists.txt project into a cmakelessfile.py.

    Raises:
        typer.Exit: With code 1 when --check finds differences.
    """
    root = source.resolve()
    script = root / BUILD_SCRIPT_NAME
    if script.exists() and not force:
        raise ConfigurationError(f"{script} already exists; pass --force to overwrite it.")
    result = import_project(root)
    script.write_text(result.script, encoding="utf-8", newline="\n")
    typer.echo(
        f"[cmakeless] wrote {script} ({result.targets} targets, {result.todos} TODO(import))"
    )
    if check:
        differences = check_import(root, result.script)
        for difference in differences:
            typer.echo(f"  {difference}")
        typer.echo(f"[cmakeless] check: {len(differences)} difference(s)")
        if differences:
            raise typer.Exit(code=1)


@app.command()
def search(term: Annotated[str, typer.Argument(help="part of a package name")]) -> None:
    """Search the dependency registry and print the depends() line to paste."""
    matches = [name for name in known_packages() if term.lower() in name.lower()]
    if not matches:
        typer.echo(
            f"[cmakeless] No registry package matches {term!r}; depends() still accepts url=."
        )
        return
    for name in matches:
        entry = registry_entry(name)
        versions = sorted(entry.sha256_by_version) if entry is not None else []
        version = versions[-1] if versions else "<version>"
        targets = ", ".join(entry.targets) if entry is not None else ""
        typer.echo(f'  {name:<16} target.depends("{name}/{version}")   # {targets}')
