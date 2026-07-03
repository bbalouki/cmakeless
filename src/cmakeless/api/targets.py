"""Mutable target builders.

Users create these via Project.add_executable() and Project.add_library();
Project.freeze() turns them into the immutable model.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from cmakeless.errors import ConfigurationError
from cmakeless.model.nodes import (
    CompileOptionsModel,
    DefineModel,
    ExecutableModel,
    LibraryKind,
    LibraryModel,
    LinkModel,
)

if TYPE_CHECKING:
    from cmakeless.api.dependencies import Dependencies, Dependency

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
    """Behavior shared by every target kind: sources, links, and settings.

    Attributes:
        name: The target's unique name (read-only property).
    """

    def __init__(
        self,
        name: str,
        sources: Sequence[str],
        *,
        script: str,
        dependencies: Dependencies,
    ) -> None:
        """Start describing a target.

        Args:
            name: Unique target name within the project.
            sources: Source files or glob patterns, project-root-relative.
            script: Display name of the owning build description, used in
                error messages.
            dependencies: The owning project's dependency collection, where
                depends() calls register their packages.
        """
        self._name = name
        self._sources: list[str] = list(sources)
        self._script = script
        self._defines: list[DefineModel] = []
        self._compile_options: list[CompileOptionsModel] = []
        self._links: list[tuple[Library, bool]] = []
        self._dependencies = dependencies
        self._dependency_links: list[tuple[Dependency, bool]] = []

    @property
    def name(self) -> str:
        """The target's unique name."""
        return self._name

    def add_sources(self, *sources: str) -> None:
        """Append more source files or glob patterns to this target.

        Args:
            *sources: Source files or glob patterns, project-root-relative.
        """
        self._sources.extend(sources)

    def define(self, name: str, value: str | int | None = None) -> None:
        """Add a preprocessor definition.

        Args:
            name: The macro name, for example ``GAME_MAX_PLAYERS``.
            value: The macro value; omit for a bare define.
        """
        self._defines.append(DefineModel(name=name, value=_format_define_value(value)))

    def compile_options(self, *flags: str, when: str | None = None) -> None:
        """Add raw compiler flags, optionally only for some compilers.

        Args:
            *flags: The flags exactly as the compiler expects them.
            when: A '|'-separated list of compiler names the flags apply to:
                "gcc", "clang", "appleclang", "msvc" (for example
                when="gcc|clang"); None applies them everywhere.

        Raises:
            ConfigurationError: When ``when`` names an unknown compiler.
        """
        self._compile_options.append(
            CompileOptionsModel(flags=tuple(flags), compilers=self._resolve_when(when))
        )

    def depends(
        self,
        spec: str,
        *,
        components: Sequence[str] = (),
        url: str | None = None,
        sha256: str | None = None,
        cmake_name: str | None = None,
        targets: Sequence[str] = (),
        public: bool = False,
    ) -> Dependency:
        """Require an external package and link its imported targets.

        Args:
            spec: The package as "name/version", for example "fmt/10.2.1".
            components: Package components, for example Boost's "asio".
            url: Source archive URL, overriding the built-in registry.
            sha256: Archive pin to verify the download against.
            cmake_name: The find_package() name, overriding the registry.
            targets: Imported target names consumers link, overriding the
                registry (for example ["fmt::fmt"]).
            public: True when this target's own headers expose the package,
                so consumers inherit it.

        Returns:
            The registered Dependency, shared across targets that require
            the same package.

        Raises:
            ConfigurationError: When the spec is malformed or conflicts
                with an earlier depends() call for the same package.
            DependencyError: When neither the registry nor the overrides
                say what CMake should see for this package.
        """
        dependency = self._dependencies.add(
            spec,
            components=components,
            url=url,
            sha256=sha256,
            cmake_name=cmake_name,
            targets=targets,
        )
        self._dependency_links.append((dependency, public))
        return dependency

    def _link(self, library: Library, public: bool) -> None:
        """Record a link edge after checking the linked object's type.

        Args:
            library: The library to link against.
            public: Whether consumers of this target inherit the dependency.

        Raises:
            ConfigurationError: When ``library`` is not a Library object.
        """
        if not isinstance(library, Library):
            raise ConfigurationError(
                f"Target {self._name!r} in {self._script} can only link Library "
                f"objects created by add_library(), got {type(library).__name__}. "
                f"For external packages use depends(), for example "
                f'target.depends("fmt/10.2.1").'
            )
        self._links.append((library, public))

    def _resolve_when(self, when: str | None) -> tuple[str, ...]:
        """Translate a when= guard into canonical compiler identifiers.

        Args:
            when: The user-facing guard string, or None for no guard.

        Returns:
            Canonical compiler ids in first-mention order; empty for None.

        Raises:
            ConfigurationError: When the guard names an unknown compiler.
        """
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
        """Expand glob patterns here in Python, where they can be validated.

        Args:
            root: Absolute project root that patterns are relative to.

        Returns:
            Root-relative source paths; glob matches are sorted.

        Raises:
            ConfigurationError: When a glob pattern matches no files.
        """
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
        """Resolve recorded link edges to model edges naming targets.

        Returns:
            One LinkModel per link() call in call order, then one per
            imported target of every depends() call.
        """
        internal = [
            LinkModel(target=library.name, public=public) for library, public in self._links
        ]
        external = [
            LinkModel(target=target, public=public, external=True)
            for dependency, public in self._dependency_links
            for target in dependency._link_targets()
        ]
        return (*internal, *external)


class Executable(_Target):
    """A runnable target being described. Frozen into an ExecutableModel."""

    def link(self, library: Library) -> None:
        """Link a library into this executable.

        Always private: nothing consumes an executable's headers.

        Args:
            library: A library created by this project's add_library().
        """
        self._link(library, public=False)

    def __repr__(self) -> str:
        """Developer-facing representation.

        Returns:
            The name and raw sources of this executable.
        """
        return f"Executable(name={self._name!r}, sources={self._sources!r})"

    def _freeze(self, root: Path) -> ExecutableModel:
        """Freeze this builder into its immutable model node.

        Args:
            root: Absolute project root used to expand source globs.

        Returns:
            The fully resolved ExecutableModel.
        """
        return ExecutableModel(
            name=self._name,
            sources=self._freeze_sources(root),
            defines=tuple(self._defines),
            compile_options=tuple(self._compile_options),
            links=self._freeze_links(),
        )


class Library(_Target):
    """A static, shared, or header-only library being described.

    Attributes:
        kind: The library kind as its string name (read-only property).
    """

    def __init__(
        self,
        name: str,
        sources: Sequence[str],
        *,
        public_headers: str | Sequence[str] = (),
        kind: LibraryKindName = "static",
        script: str,
        dependencies: Dependencies,
    ) -> None:
        """Start describing a library.

        Args:
            name: Unique target name within the project.
            sources: Source files or glob patterns; empty for header-only.
            public_headers: Directory (or directories) whose headers
                consumers may include.
            kind: "static", "shared", or "header_only".
            script: Display name of the owning build description, used in
                error messages.
            dependencies: The owning project's dependency collection, where
                depends() calls register their packages.

        Raises:
            ConfigurationError: When ``kind`` is not a known library kind.
        """
        super().__init__(name, sources, script=script, dependencies=dependencies)
        self._kind = self._resolve_kind(kind)
        headers = [public_headers] if isinstance(public_headers, str) else list(public_headers)
        self._public_headers: list[str] = headers

    @property
    def kind(self) -> str:
        """The library kind: "static", "shared", or "header_only"."""
        return self._kind.value

    def link(self, library: Library, *, public: bool = False) -> None:
        """Link another library into this one.

        Args:
            library: A library created by this project's add_library().
            public: True when this library's own headers expose the linked
                one, so consumers inherit the dependency.
        """
        self._link(library, public=public)

    def __repr__(self) -> str:
        """Developer-facing representation.

        Returns:
            The name, kind, and raw sources of this library.
        """
        return f"Library(name={self._name!r}, kind={self._kind.value!r}, sources={self._sources!r})"

    def _resolve_kind(self, kind: str) -> LibraryKind:
        """Translate the user-facing kind string into the model enum.

        Args:
            kind: The kind name given to add_library().

        Returns:
            The matching LibraryKind member.

        Raises:
            ConfigurationError: When the kind is not a known library kind.
        """
        try:
            return LibraryKind(kind)
        except ValueError:
            kinds = ", ".join(repr(member.value) for member in LibraryKind)
            raise ConfigurationError(
                f"Unknown library kind {kind!r} for {self._name!r} in {self._script}. "
                f"Pick one of: {kinds}."
            ) from None

    def _freeze(self, root: Path) -> LibraryModel:
        """Freeze this builder into its immutable model node.

        Args:
            root: Absolute project root used to expand source globs.

        Returns:
            The fully resolved LibraryModel.
        """
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
    """Normalize a define value to the string form the model stores.

    Args:
        value: The user-supplied value, or None for a bare define.

    Returns:
        The value as a string, or None when no value was given.
    """
    if value is None:
        return None
    return str(value)
