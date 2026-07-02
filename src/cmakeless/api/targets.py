"""Mutable target builders. Users create these via Project.add_executable()
and Project.add_library()."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from cmakeless.errors import ConfigurationError
from cmakeless.model.nodes import (
    CompileOptionsModel,
    DefineModel,
    ExecutableModel,
    LibraryKind,
    LibraryModel,
    LinkModel,
)

type LibraryKindName = Literal["static", "shared", "header_only"]

_GLOB_CHARACTERS = frozenset("*?[")

# Friendly compiler names accepted in when= guards, mapped to canonical ids.
_COMPILERS_BY_TOKEN: dict[str, tuple[str, ...]] = {
    "gcc": ("gnu",),
    "clang": ("clang", "appleclang"),
    "appleclang": ("appleclang",),
    "msvc": ("msvc",),
}


class _Target:
    """Behavior shared by every target kind: sources, links, and settings."""

    def __init__(self, name: str, sources: Sequence[str], *, script: str) -> None:
        self._name = name
        self._sources: list[str] = list(sources)
        self._script = script
        self._defines: list[DefineModel] = []
        self._compile_options: list[CompileOptionsModel] = []
        self._links: list[tuple[Library, bool]] = []

    @property
    def name(self) -> str:
        return self._name

    def add_sources(self, *sources: str) -> None:
        """Append more source files or glob patterns to this target."""
        self._sources.extend(sources)

    def define(self, name: str, value: str | int | None = None) -> None:
        """Add a preprocessor definition; omit the value for a bare define."""
        self._defines.append(DefineModel(name=name, value=_format_define_value(value)))

    def compile_options(self, *flags: str, when: str | None = None) -> None:
        """Add raw compiler flags, optionally only for some compilers.

        The when= guard is a '|'-separated list of compiler names:
        "gcc", "clang", "appleclang", "msvc" (for example when="gcc|clang").
        """
        self._compile_options.append(
            CompileOptionsModel(flags=tuple(flags), compilers=self._resolve_when(when))
        )

    def _link(self, library: Library, public: bool) -> None:
        if not isinstance(library, Library):
            raise ConfigurationError(
                f"Target {self._name!r} in {self._script} can only link Library "
                f"objects created by add_library(), got {type(library).__name__}. "
                f"External packages arrive with depends() in a later release."
            )
        self._links.append((library, public))

    def _resolve_when(self, when: str | None) -> tuple[str, ...]:
        if when is None:
            return ()
        compilers: list[str] = []
        for token in when.split("|"):
            normalized = token.strip().lower()
            if normalized not in _COMPILERS_BY_TOKEN:
                known = ", ".join(sorted(_COMPILERS_BY_TOKEN))
                raise ConfigurationError(
                    f"Unknown compiler {token!r} in when= guard on target "
                    f"{self._name!r} in {self._script}. Use a '|'-separated list "
                    f'of: {known} (for example when="gcc|clang").'
                )
            compilers.extend(
                compiler
                for compiler in _COMPILERS_BY_TOKEN[normalized]
                if compiler not in compilers
            )
        return tuple(compilers)

    def _freeze_sources(self, root: Path) -> tuple[Path, ...]:
        """Expand glob patterns here in Python, where they can be validated."""
        resolved: list[Path] = []
        for entry in self._sources:
            if _GLOB_CHARACTERS.isdisjoint(entry):
                resolved.append(Path(entry))
                continue
            matches = sorted(path.relative_to(root) for path in root.glob(entry) if path.is_file())
            if not matches:
                raise ConfigurationError(
                    f"Source pattern '{entry}' for target {self._name!r} matched no "
                    f"files under {root}. Check the pattern in {self._script} for a "
                    f"typo, or create the files."
                )
            resolved.extend(matches)
        return tuple(resolved)

    def _freeze_links(self) -> tuple[LinkModel, ...]:
        return tuple(
            LinkModel(target=library.name, public=public) for library, public in self._links
        )


class Executable(_Target):
    """A runnable target being described. Frozen into an ExecutableModel."""

    def link(self, library: Library) -> None:
        """Link a library into this executable (always private: nothing consumes
        an executable's headers)."""
        self._link(library, public=False)

    def __repr__(self) -> str:
        return f"Executable(name={self._name!r}, sources={self._sources!r})"

    def _freeze(self, root: Path) -> ExecutableModel:
        return ExecutableModel(
            name=self._name,
            sources=self._freeze_sources(root),
            defines=tuple(self._defines),
            compile_options=tuple(self._compile_options),
            links=self._freeze_links(),
        )


class Library(_Target):
    """A static, shared, or header-only library being described."""

    def __init__(
        self,
        name: str,
        sources: Sequence[str],
        *,
        public_headers: str | Sequence[str] = (),
        kind: LibraryKindName = "static",
        script: str,
    ) -> None:
        super().__init__(name, sources, script=script)
        self._kind = self._resolve_kind(kind)
        headers = [public_headers] if isinstance(public_headers, str) else list(public_headers)
        self._public_headers: list[str] = headers

    @property
    def kind(self) -> str:
        return self._kind.value

    def link(self, library: Library, *, public: bool = False) -> None:
        """Link another library; public=True when this library's own headers
        expose it, so consumers inherit the dependency."""
        self._link(library, public=public)

    def __repr__(self) -> str:
        return f"Library(name={self._name!r}, kind={self._kind.value!r}, sources={self._sources!r})"

    def _resolve_kind(self, kind: str) -> LibraryKind:
        try:
            return LibraryKind(kind)
        except ValueError:
            kinds = ", ".join(repr(member.value) for member in LibraryKind)
            raise ConfigurationError(
                f"Unknown library kind {kind!r} for {self._name!r} in {self._script}. "
                f"Pick one of: {kinds}."
            ) from None

    def _freeze(self, root: Path) -> LibraryModel:
        return LibraryModel(
            name=self._name,
            kind=self._kind,
            sources=self._freeze_sources(root),
            public_include_dirs=tuple(Path(header) for header in self._public_headers),
            defines=tuple(self._defines),
            compile_options=tuple(self._compile_options),
            links=self._freeze_links(),
        )


def _format_define_value(value: str | int | None) -> str | None:
    if value is None:
        return None
    return str(value)
