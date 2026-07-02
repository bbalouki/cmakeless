"""Mutable target builders. Users create these via Project.add_executable()."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from cmakeless.model.nodes import ExecutableModel


class Executable:
    """A runnable target being described. Frozen into an ExecutableModel by the project."""

    def __init__(self, name: str, sources: Sequence[str]) -> None:
        self._name = name
        self._sources: list[str] = list(sources)

    @property
    def name(self) -> str:
        return self._name

    def add_sources(self, *sources: str) -> None:
        """Append more source files to this target."""
        self._sources.extend(sources)

    def __repr__(self) -> str:
        return f"Executable(name={self._name!r}, sources={self._sources!r})"

    def _freeze(self) -> ExecutableModel:
        # PureWindowsPath-safe normalization happens here: users may write
        # either separator, the model always holds forward-slash-friendly Paths.
        sources = tuple(Path(source) for source in self._sources)
        return ExecutableModel(name=self._name, sources=sources)
