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
