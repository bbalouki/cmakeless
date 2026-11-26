"""Private runtime context shared between the CLI and the API layer.

Two pieces of state live here:

- Description mode: while a parent project loads a subproject's
  cmakelessfile.py, the child's Project must register itself instead of
  building. A capture stack makes the child's project.build() call a
  harmless no-op.
- Verb override: 'cmakeless configure' runs the same cmakelessfile.py as
  'cmakeless build'; the override tells the project.build() facade which
  verb the user actually asked for.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from cmakeless.errors import ConfigurationError

if TYPE_CHECKING:
    from cmakeless.api.project import Project

_capture_stack: list[list[Project]] = []
_loading_scripts: list[Path] = []
_verb_override: list[str] = []
_generator_override: list[str] = []
_preset_override: list[str] = []
_sanitize_override: list[tuple[str, ...]] = []
_prefix_override: list[str] = []
_offline_override: list[bool] = []
_sbom_format_override: list[str] = []
_sbom_output_override: list[str] = []
_vendor_directory_override: list[str] = []


@contextmanager
def capturing_projects() -> Generator[list[Project]]:
    """Enter description mode; projects created inside are captured, not built.

    Yields:
        The live list that collects every Project constructed while the
        context is active.
    """
    captured: list[Project] = []
    _capture_stack.append(captured)
    try:
        yield captured
    finally:
        _capture_stack.pop()


def register_project(project: Project) -> None:
    """Hand a freshly constructed project to the active capture list, if any.

    Args:
        project: The project that was just constructed.
    """
    if _capture_stack:
        _capture_stack[-1].append(project)


def in_description_mode() -> bool:
    """Tell whether a subproject's cmakelessfile.py is currently being loaded.

    Returns:
        True while at least one capturing_projects() context is active.
    """
    return bool(_capture_stack)


@contextmanager
def loading_script(script: Path) -> Generator[None]:
    """Guard against subproject recursion (a child adding its own ancestor).

    Args:
        script: The cmakelessfile.py about to be executed.

    Yields:
        Nothing; the guard is active for the duration of the context.

    Raises:
        ConfigurationError: When the script is already being loaded higher
            up the chain, which would recurse forever.
    """
    resolved = script.resolve()
    if resolved in _loading_scripts:
        chain = " -> ".join(str(path) for path in [*_loading_scripts, resolved])
        raise ConfigurationError(
            f"Subproject cycle detected: {chain}. A subproject cannot add one of "
            f"its own ancestors; remove the add_subproject() call that closes "
            f"the loop."
        )
    _loading_scripts.append(resolved)
    try:
        yield
    finally:
        _loading_scripts.pop()


@contextmanager
def verb_override(verb: str) -> Generator[None]:
    """Make project.build() perform the given CLI verb instead of a full build.

    Args:
        verb: The verb the CLI user asked for ("build", "configure", "clean").

    Yields:
        Nothing; the override is active for the duration of the context.
    """
    _verb_override.append(verb)
    try:
        yield
    finally:
        _verb_override.pop()


def active_verb() -> str:
    """Look up the verb project.build() should perform.

    Returns:
        The innermost overridden verb, or "build" when none is active.
    """
    return _verb_override[-1] if _verb_override else "build"


@contextmanager
def generator_override(generator: str | None) -> Generator[None]:
    """Make projects prefer the generator the CLI user asked for.

    Args:
        generator: The generator name from --generator, or None for no
            preference (the context is then a no-op).

    Yields:
        Nothing; the override is active for the duration of the context.
    """
    if generator is None:
        yield
        return
    _generator_override.append(generator)
    try:
        yield
    finally:
        _generator_override.pop()


def active_generator() -> str | None:
    """Look up the generator preference set by the CLI.

    Returns:
        The innermost overridden generator name, or None when unset.
    """
    return _generator_override[-1] if _generator_override else None


@contextmanager
def preset_override(preset: str | None) -> Generator[None]:
    """Make projects configure and build with the preset the CLI asked for.

    Args:
        preset: The preset name from --preset, or None for no preference
            (the context is then a no-op).

    Yields:
        Nothing; the override is active for the duration of the context.
    """
    if preset is None:
        yield
        return
    _preset_override.append(preset)
    try:
        yield
    finally:
        _preset_override.pop()


def active_preset() -> str | None:
    """Look up the preset preference set by the CLI.

    Returns:
        The innermost overridden preset name, or None when unset.
    """
    return _preset_override[-1] if _preset_override else None


@contextmanager
def sanitize_override(sanitizers: tuple[str, ...]) -> Generator[None]:
    """Make 'cmakeless test' run under the given sanitizers.

    Args:
        sanitizers: Sanitizer names from --sanitize; empty makes the
            context a no-op.

    Yields:
        Nothing; the override is active for the duration of the context.
    """
    if not sanitizers:
        yield
        return
    _sanitize_override.append(sanitizers)
    try:
        yield
    finally:
        _sanitize_override.pop()


def active_sanitize() -> tuple[str, ...]:
    """Look up the sanitizer selection set by the CLI.

    Returns:
        The innermost overridden sanitizer names, or an empty tuple.
    """
    return _sanitize_override[-1] if _sanitize_override else ()


@contextmanager
def prefix_override(prefix: str | None) -> Generator[None]:
    """Make 'cmakeless install' install into the given prefix.

    Args:
        prefix: The installation prefix from --prefix, or None for
            CMake's default (the context is then a no-op).

    Yields:
        Nothing; the override is active for the duration of the context.
    """
    if prefix is None:
        yield
        return
    _prefix_override.append(prefix)
    try:
        yield
    finally:
        _prefix_override.pop()


def active_prefix() -> str | None:
    """Look up the installation prefix set by the CLI.

    Returns:
        The innermost overridden prefix, or None when unset.
    """
    return _prefix_override[-1] if _prefix_override else None


@contextmanager
def offline_override(offline: bool) -> Generator[None]:
    """Make dependency resolution and package-manager installs run --offline.

    Args:
        offline: True to disallow network access during resolution;
            False is a no-op (the context still pushes/pops, harmlessly).

    Yields:
        Nothing; the override is active for the duration of the context.
    """
    _offline_override.append(offline)
    try:
        yield
    finally:
        _offline_override.pop()


def active_offline() -> bool:
    """Look up whether --offline is active.

    Returns:
        The innermost overridden value, or False when unset.
    """
    return _offline_override[-1] if _offline_override else False


@contextmanager
def sbom_format_override(format_name: str) -> Generator[None]:
    """Make 'cmakeless sbom' write the given SBOM format.

    Args:
        format_name: "cyclonedx" or "spdx", from --format.

    Yields:
        Nothing; the override is active for the duration of the context.
    """
    _sbom_format_override.append(format_name)
    try:
        yield
    finally:
        _sbom_format_override.pop()


def active_sbom_format() -> str:
    """Look up the SBOM format set by the CLI.

    Returns:
        The innermost overridden format, or "cyclonedx" when unset.
    """
    return _sbom_format_override[-1] if _sbom_format_override else "cyclonedx"


@contextmanager
def sbom_output_override(output: str | None) -> Generator[None]:
    """Make 'cmakeless sbom' write to the given path.

    Args:
        output: The path from --output, or None for no preference (the
            context is then a no-op).

    Yields:
        Nothing; the override is active for the duration of the context.
    """
    if output is None:
        yield
        return
    _sbom_output_override.append(output)
    try:
        yield
    finally:
        _sbom_output_override.pop()


def active_sbom_output() -> str | None:
    """Look up the SBOM output path set by the CLI.

    Returns:
        The innermost overridden path, or None when unset.
    """
    return _sbom_output_override[-1] if _sbom_output_override else None


@contextmanager
def vendor_directory_override(directory: str | None) -> Generator[None]:
    """Make 'cmakeless vendor' download into the given directory.

    Args:
        directory: The path from --directory, or None for no preference
            (the context is then a no-op).

    Yields:
        Nothing; the override is active for the duration of the context.
    """
    if directory is None:
        yield
        return
    _vendor_directory_override.append(directory)
    try:
        yield
    finally:
        _vendor_directory_override.pop()


def active_vendor_directory() -> str | None:
    """Look up the vendor directory set by the CLI.

    Returns:
        The innermost overridden path, or None when unset.
    """
    return _vendor_directory_override[-1] if _vendor_directory_override else None


@dataclass(frozen=True, slots=True)
class RunOptions:
    """Every per-run CLI knob added after 1.0, carried as one value.

    The older flags each have their own override above and keep it, so
    nothing that reads them changes; new flags land here instead of growing
    one more stack per flag.

    Attributes:
        target: Build only this target, or None for everything.
        jobs: Parallel build or test jobs, or None for the tool default.
        config: The configuration for multi-config generators, or None.
        verbose: True to show the real compiler and linker command lines.
        fresh: True to discard the CMake cache before configuring.
        defines: Extra -D cache settings as (name, value) pairs.
        test_filter: A CTest -R regular expression, or None.
        test_label: A CTest -L label expression, or None.
        test_repeat: Run each test until it fails, up to this many times.
        junit: Where CTest writes JUnit XML, or None.
        instrumentation: Instrumentation names active for this run.
        program_args: Arguments for 'cmakeless run'.
        lock_packages: Packages 'cmakeless lock --package' refreshes.
        subject: What 'explain' explains or 'fuzz' fuzzes, or None.
        fuzz_seconds: How long 'cmakeless fuzz' runs.
        train: The training command line 'cmakeless pgo' runs.
        presets: The presets 'cmakeless matrix' builds; empty for all.
        report: The report format a verb writes ("text", "json", "sarif").
        output: Where a verb writes its report or bundle, or None.
        exit_code: True when 'cmakeless diff' should fail on any change.
        approve: Packages 'cmakeless audit --approve' marks as reviewed.
        workspace_project: The one workspace member to run, or None for all.
        affected_since: A git revision; only workspace members changed
            since it run.
        json_events: True to stream every progress event as JSON lines
            instead of the console display.
    """

    target: str | None = None
    jobs: int | None = None
    config: str | None = None
    verbose: bool = False
    fresh: bool = False
    defines: tuple[tuple[str, str], ...] = ()
    test_filter: str | None = None
    test_label: str | None = None
    test_repeat: int | None = None
    junit: str | None = None
    instrumentation: tuple[str, ...] = ()
    program_args: tuple[str, ...] = ()
    lock_packages: tuple[str, ...] = ()
    subject: str | None = None
    fuzz_seconds: int = 60
    train: str | None = None
    presets: tuple[str, ...] = ()
    report: str = "text"
    output: str | None = None
    exit_code: bool = False
    approve: tuple[str, ...] = ()
    workspace_project: str | None = None
    affected_since: str | None = None
    json_events: bool = False


_run_options_override: list[RunOptions] = []


@contextmanager
def run_options_override(options: RunOptions) -> Generator[None]:
    """Make the given run options visible to the pipeline.

    Args:
        options: The options the CLI parsed for this run.

    Yields:
        Nothing; the options are active for the duration of the context.
    """
    _run_options_override.append(options)
    try:
        yield
    finally:
        _run_options_override.pop()


def active_run_options() -> RunOptions:
    """Look up the run options set by the CLI.

    Returns:
        The innermost options, or the defaults outside the CLI.
    """
    return _run_options_override[-1] if _run_options_override else RunOptions()


_lock_path_override: list[Path] = []


@contextmanager
def lock_path_override(path: Path) -> Generator[None]:
    """Make every project share one lockfile, as a workspace does.

    Args:
        path: The shared lockfile.

    Yields:
        Nothing; the override is active for the duration of the context.
    """
    _lock_path_override.append(path)
    try:
        yield
    finally:
        _lock_path_override.pop()


def active_lock_path() -> Path | None:
    """Look up the shared lockfile, if a workspace set one.

    Returns:
        The innermost override, or None for each project's own lockfile.
    """
    return _lock_path_override[-1] if _lock_path_override else None
