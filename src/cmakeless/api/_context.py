"""Private runtime context shared between the CLI and the API layer.

Two pieces of state live here:

- Description mode: while a parent project loads a subproject's build.py, the
  child's Project must register itself instead of building. A capture stack
  makes the child's project.build() call a harmless no-op.
- Verb override: 'cmakeless configure' runs the same build.py as 'cmakeless
  build'; the override tells the project.build() facade which verb the user
  actually asked for.
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


@contextmanager
def capturing_projects() -> Generator[list[Project]]:
    """Enter description mode; projects created inside are captured, not built."""
    captured: list[Project] = []
    _capture_stack.append(captured)
    try:
        yield captured
    finally:
        _capture_stack.pop()


def register_project(project: Project) -> None:
    if _capture_stack:
        _capture_stack[-1].append(project)


def in_description_mode() -> bool:
    return bool(_capture_stack)


@contextmanager
def loading_script(script: Path) -> Generator[None]:
    """Guard against subproject recursion (a child adding its own ancestor)."""
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
    """Make project.build() perform the given CLI verb instead of a full build."""
    _verb_override.append(verb)
    try:
        yield
    finally:
        _verb_override.pop()


def active_verb() -> str:
    return _verb_override[-1] if _verb_override else "build"


@contextmanager
def generator_override(generator: str | None) -> Generator[None]:
    """Make projects prefer the generator the CLI user asked for."""
    if generator is None:
        yield
        return
    _generator_override.append(generator)
    try:
        yield
    finally:
        _generator_override.pop()


def active_generator() -> str | None:
    return _generator_override[-1] if _generator_override else None
