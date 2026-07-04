# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Mutable target builders.

Users create these via Project.add_executable() and Project.add_library();
Project.freeze() turns them into the immutable model.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from cmakeless._constants import MIN_PYTHON_VERSION
from cmakeless.api.commands import Command
from cmakeless.api.when import When
from cmakeless.errors import ConfigurationError
from cmakeless.model.nodes import (
    PYTHON_BINDING_BACKENDS,
    TEST_FRAMEWORKS,
    CompileOptionsModel,
    DefineModel,
    ExecutableModel,
    LibraryKind,
    LibraryModel,
    LinkModel,
    LinkOptionsModel,
    PythonModuleModel,
    TestModel,
    WhenModel,
)

if TYPE_CHECKING:
    from cmakeless.api.dependencies import Dependencies, Dependency
    from cmakeless.api.options import Option

type LibraryKindName = Literal["static", "shared", "header_only"]
type TestFrameworkName = Literal["gtest", "catch2", "doctest", "none"]
type PythonBindingName = Literal["pybind11", "nanobind"]
type WhenArgument = str | When | Option | None

_GLOB_CHARACTERS = frozenset("*?[")


class _Target:
    """Behavior shared by every target kind: sources, links, and settings.

    Attributes:
        name: The target's unique name (read-only property).
        sanitize: Sanitizer names ("address", "undefined", "thread",
            "leak") applied to this target's compile and link steps; plain
            attribute, assign a list to change it.
        cpp_std: This target's own C++ standard, overriding the project's;
            plain attribute, assign an int to change it, or leave it None
            to use the project's cpp_std.
        pch: Headers to precompile for this target; plain attribute,
            assign a list of headers (angle-bracket system headers like
            "<vector>", or project-relative paths) to change it.
        unity: True to build this target as a single unity translation
            unit; plain attribute, assign a bool to change it.

    Use raw_cmake() to emit CMake this API does not model, verbatim, after
    the target is defined. Use lint() to override project.lint()'s
    clang-tidy/IWYU setting for this target alone.
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
        self.sanitize: Sequence[str] = []
        self.cpp_std: int | None = None
        self.pch: Sequence[str] = []
        self.unity: bool = False
        self._lint_clang_tidy: tuple[str, ...] | None = None
        self._lint_iwyu: tuple[str, ...] | None = None
        self._defines: list[DefineModel] = []
        self._compile_options: list[CompileOptionsModel] = []
        self._link_options: list[LinkOptionsModel] = []
        self._links: list[tuple[Library, bool]] = []
        self._dependencies = dependencies
        self._dependency_links: list[tuple[Dependency, bool]] = []
        self._raw_cmake: list[str] = []
        self._private_include_dirs: list[str] = []
        self._generated_sources: set[str] = set()

    @property
    def name(self) -> str:
        """The target's unique name."""
        return self._name

    def add_sources(self, *sources: str | Command) -> None:
        """Append more source files, glob patterns, or a Command's output.

        Args:
            *sources: Source files or glob patterns, project-root-relative,
                or a Command handle (its declared outputs are added as
                sources; they are not checked for existence at freeze time,
                since a command's output does not exist until it runs).
        """
        for source in sources:
            if isinstance(source, Command):
                self._sources.extend(source.outputs)
                self._generated_sources.update(source.outputs)
            else:
                self._sources.append(source)

    def include_dirs(self, *dirs: str) -> None:
        """Add directories, private to this target, that its own sources may #include.

        Contrast with Library(public_headers=...), which exposes headers to
        consumers (PUBLIC/INTERFACE); these directories never leave this
        target's own compile step.

        Args:
            *dirs: Directories, project-root-relative, to add as private
                include directories.
        """
        self._private_include_dirs.extend(dirs)

    def define(
        self, name: str, value: str | int | None = None, *, when: WhenArgument = None
    ) -> None:
        """Add a preprocessor definition.

        Args:
            name: The macro name, for example ``GAME_MAX_PLAYERS``.
            value: The macro value; omit for a bare define.
            when: A condition guarding the define (see When), a
                '|'-separated compiler-name string (sugar for
                When.compiler(...)), an Option (sugar for When.option(...)),
                or None to apply it unconditionally.

        Raises:
            ConfigurationError: When ``when`` is a string naming an unknown
                compiler.
        """
        self._defines.append(
            DefineModel(name=name, value=_format_define_value(value), when=self._resolve_when(when))
        )

    def compile_options(self, *flags: str, when: WhenArgument = None) -> None:
        """Add raw compiler flags, optionally guarded by a condition.

        Args:
            *flags: The flags exactly as the compiler expects them.
            when: A condition guarding the flags (see When), a
                '|'-separated compiler-name string (sugar for
                When.compiler(...), for example when="gcc|clang"), an
                Option (sugar for When.option(...)), or None to apply them
                unconditionally.

        Raises:
            ConfigurationError: When ``when`` is a string naming an unknown
                compiler.
        """
        self._compile_options.append(
            CompileOptionsModel(flags=tuple(flags), when=self._resolve_when(when))
        )

    def link_options(self, *flags: str, when: WhenArgument = None) -> None:
        """Add raw linker flags, optionally guarded by a condition.

        Args:
            *flags: The flags exactly as the linker expects them.
            when: A condition guarding the flags (see When), a
                '|'-separated compiler-name string (sugar for
                When.compiler(...)), an Option (sugar for When.option(...)),
                or None to apply them unconditionally.

        Raises:
            ConfigurationError: When ``when`` is a string naming an unknown
                compiler.
        """
        self._link_options.append(
            LinkOptionsModel(flags=tuple(flags), when=self._resolve_when(when))
        )

    def raw_cmake(self, snippet: str) -> None:
        """Emit a raw CMake snippet verbatim after this target is defined.

        The escape hatch for the 1% CMakeless does not model: the text is
        written into the generated CMakeLists.txt exactly as given, fenced
        with a comment naming its cmakelessfile.py origin. Snippets are emitted in
        the order added; nothing about them is validated.

        Args:
            snippet: The CMake to emit, for example
                ``set_property(TARGET engine PROPERTY JOB_POOL_COMPILE heavy_jobs)``.

        Raises:
            ConfigurationError: When the snippet is empty or only whitespace.
        """
        if not snippet.strip():
            raise ConfigurationError(
                f"Empty raw_cmake() snippet on target {self._name!r} in "
                f"{self._script}. Pass the CMake to emit, or remove the call."
            )
        self._raw_cmake.append(snippet)

    def lint(
        self, *, clang_tidy: bool | Sequence[str] = False, iwyu: bool | Sequence[str] = False
    ) -> None:
        """Override project.lint()'s clang-tidy/IWYU setting for this target alone.

        Once called, this target's own setting always wins over the
        project's, including calling lint() with both arguments False to
        opt this target out of a project-wide default.

        Args:
            clang_tidy: True to run clang-tidy with its own defaults, a
                sequence to pass the command and extra arguments (for
                example ["clang-tidy", "-checks=-*,modernize-*"]), or False
                to disable it for this target.
            iwyu: True to run include-what-you-use, a sequence for the
                command and extra arguments, or False to disable it for
                this target.
        """
        self._lint_clang_tidy = _lint_tool_names(clang_tidy, tool="clang-tidy")
        self._lint_iwyu = _lint_tool_names(iwyu, tool="include-what-you-use")

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

    def _resolve_when(self, when: WhenArgument) -> WhenModel | None:
        """Normalize a when= argument to the model's condition tree.

        Args:
            when: None for no guard; a '|'-separated compiler-name string
                (kept as sugar for When.compiler(...), for example
                when="gcc|clang"); an Option (sugar for When.option(...));
                or a When value built from its factory methods.

        Returns:
            The frozen WhenModel, or None for no guard.

        Raises:
            ConfigurationError: When a string names an unknown compiler.
        """
        if when is None:
            return None
        if isinstance(when, When):
            return when._freeze()
        if isinstance(when, str):
            return When.compiler(*when.split("|"))._freeze()
        return When.option(when)._freeze()

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
            if entry in self._generated_sources or _GLOB_CHARACTERS.isdisjoint(entry):
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

    def _freeze_private_include_dirs(self) -> tuple[Path, ...]:
        """Normalize the private include dirs into the model's path tuple.

        Returns:
            The requested directories as Path objects, in call order;
            existence is checked on the frozen model.
        """
        return tuple(Path(directory) for directory in self._private_include_dirs)

    def _freeze_pch(self) -> tuple[str, ...]:
        """Normalize the pch attribute into the model's header tuple.

        Returns:
            The requested headers in call order; existence (for
            project-relative entries) is checked on the frozen model.
        """
        return tuple(self.pch)

    def _freeze_sanitize(self) -> tuple[str, ...]:
        """Normalize the sanitize attribute into the model's sorted tuple.

        Returns:
            The requested sanitizer names, deduplicated and sorted; name
            validation happens on the frozen model.
        """
        return tuple(sorted(set(self.sanitize)))

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
            link_options=tuple(self._link_options),
            links=self._freeze_links(),
            sanitize=self._freeze_sanitize(),
            raw_cmake=tuple(self._raw_cmake),
            private_include_dirs=self._freeze_private_include_dirs(),
            cpp_std=self.cpp_std,
            pch_headers=self._freeze_pch(),
            unity=self.unity,
            clang_tidy=self._lint_clang_tidy,
            iwyu=self._lint_iwyu,
        )


class Test(_Target):
    """A test executable being described. Frozen into a TestModel.

    Created via Project.add_test(); the framework's package registration
    and link edge are handled there, so a Test builder only adds sources,
    links, and settings like any other target.
    """

    # Tell pytest this builder is not a test case, despite the name.
    __test__ = False

    def __init__(
        self,
        name: str,
        sources: Sequence[str],
        *,
        framework: TestFrameworkName = "gtest",
        script: str,
        dependencies: Dependencies,
    ) -> None:
        """Start describing a test.

        Args:
            name: Unique target name within the project.
            sources: Source files or glob patterns, project-root-relative.
            framework: "gtest" (the default), "catch2", "doctest", or "none"
                for a plain executable whose exit code is the verdict.
            script: Display name of the owning build description, used in
                error messages.
            dependencies: The owning project's dependency collection.

        Raises:
            ConfigurationError: When ``framework`` is not a known one.
        """
        super().__init__(name, sources, script=script, dependencies=dependencies)
        if framework not in TEST_FRAMEWORKS:
            frameworks = ", ".join(repr(known) for known in sorted(TEST_FRAMEWORKS))
            raise ConfigurationError(
                f"Unknown test framework {framework!r} for test {self._name!r} in "
                f"{self._script}. Pick one of: {frameworks}."
            )
        self._framework: str = framework

    @property
    def framework(self) -> str:
        """The test framework: "gtest", "catch2", "doctest", or "none"."""
        return self._framework

    def link(self, library: Library) -> None:
        """Link a library into this test.

        Always private: nothing consumes a test's headers.

        Args:
            library: A library created by this project's add_library().
        """
        self._link(library, public=False)

    def __repr__(self) -> str:
        """Developer-facing representation.

        Returns:
            The name, framework, and raw sources of this test.
        """
        return (
            f"Test(name={self._name!r}, framework={self._framework!r}, sources={self._sources!r})"
        )

    def _freeze(self, root: Path) -> TestModel:
        """Freeze this builder into its immutable model node.

        Args:
            root: Absolute project root used to expand source globs.

        Returns:
            The fully resolved TestModel.
        """
        return TestModel(
            name=self._name,
            sources=self._freeze_sources(root),
            framework=self._framework,
            defines=tuple(self._defines),
            compile_options=tuple(self._compile_options),
            link_options=tuple(self._link_options),
            links=self._freeze_links(),
            sanitize=self._freeze_sanitize(),
            raw_cmake=tuple(self._raw_cmake),
            private_include_dirs=self._freeze_private_include_dirs(),
            cpp_std=self.cpp_std,
            pch_headers=self._freeze_pch(),
            unity=self.unity,
            clang_tidy=self._lint_clang_tidy,
            iwyu=self._lint_iwyu,
        )


class PythonModule(_Target):
    """A Python extension module being described. Frozen into a PythonModuleModel.

    Created via Project.add_python_module(); the binding backend's package
    registration is handled there, so a PythonModule builder only adds
    sources, links, and settings like any other target.

    Attributes:
        binding: The binding backend ("pybind11" or "nanobind"),
            read-only property.
    """

    def __init__(
        self,
        name: str,
        sources: Sequence[str],
        *,
        binding: PythonBindingName = "pybind11",
        stubs: bool = True,
        install: bool = True,
        python_version: str | None = None,
        script: str,
        dependencies: Dependencies,
    ) -> None:
        """Start describing a Python extension module.

        Args:
            name: The importable module name and unique target name.
            sources: Source files or glob patterns, project-root-relative.
            binding: "pybind11" (the default) or "nanobind".
            stubs: True to generate a .pyi stub (nanobind only).
            install: True to copy the built module into the invoking
                interpreter after build, so it imports immediately.
            python_version: The minimum Python version find_package(Python
                ...) requires, as "MAJOR.MINOR" (for example "3.12"), or
                None (the default) to use CMakeless's own supported floor.
                Independent of whichever interpreter happens to run
                cmakeless, so the generated CMake stays deterministic.
            script: Display name of the owning build description, used in
                error messages.
            dependencies: The owning project's dependency collection.

        Raises:
            ConfigurationError: When ``binding`` is not a known backend, or
                ``python_version`` is not a well-formed "MAJOR.MINOR" string.
        """
        super().__init__(name, sources, script=script, dependencies=dependencies)
        if binding not in PYTHON_BINDING_BACKENDS:
            backends = ", ".join(repr(known) for known in sorted(PYTHON_BINDING_BACKENDS))
            raise ConfigurationError(
                f"Unknown binding backend {binding!r} for Python module {self._name!r} "
                f"in {self._script}. Pick one of: {backends}."
            )
        self._binding: str = binding
        self._stubs = stubs
        self._install = install
        self._python_version = _resolve_python_version(
            python_version, name=self._name, script=self._script
        )

    @property
    def binding(self) -> str:
        """The binding backend: "pybind11" or "nanobind"."""
        return self._binding

    def link(self, library: Library) -> None:
        """Link a library into this module.

        Always private: nothing consumes a module's headers.

        Args:
            library: A library created by this project's add_library().
        """
        self._link(library, public=False)

    def __repr__(self) -> str:
        """Developer-facing representation.

        Returns:
            The name, binding, and raw sources of this module.
        """
        return (
            f"PythonModule(name={self._name!r}, binding={self._binding!r}, "
            f"sources={self._sources!r})"
        )

    def _freeze(self, root: Path) -> PythonModuleModel:
        """Freeze this builder into its immutable model node.

        Args:
            root: Absolute project root used to expand source globs.

        Returns:
            The fully resolved PythonModuleModel.
        """
        return PythonModuleModel(
            name=self._name,
            sources=self._freeze_sources(root),
            binding=self._binding,
            stubs=self._stubs,
            install_to_environment=self._install,
            python_version=self._python_version,
            defines=tuple(self._defines),
            compile_options=tuple(self._compile_options),
            link_options=tuple(self._link_options),
            links=self._freeze_links(),
            sanitize=self._freeze_sanitize(),
            raw_cmake=tuple(self._raw_cmake),
            private_include_dirs=self._freeze_private_include_dirs(),
            cpp_std=self.cpp_std,
            pch_headers=self._freeze_pch(),
            unity=self.unity,
            clang_tidy=self._lint_clang_tidy,
            iwyu=self._lint_iwyu,
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
            link_options=tuple(self._link_options),
            links=self._freeze_links(),
            sanitize=self._freeze_sanitize(),
            raw_cmake=tuple(self._raw_cmake),
            private_include_dirs=self._freeze_private_include_dirs(),
            cpp_std=self.cpp_std,
            pch_headers=self._freeze_pch(),
            unity=self.unity,
            clang_tidy=self._lint_clang_tidy,
            iwyu=self._lint_iwyu,
        )


def _lint_tool_names(value: bool | Sequence[str], *, tool: str) -> tuple[str, ...]:
    """Normalize a lint()/Project.lint() argument to its command tuple.

    Args:
        value: True for the tool's own defaults, a sequence for the command
            and extra arguments, or False to disable it.
        tool: The tool's default command name ("clang-tidy" or
            "include-what-you-use"), used when ``value`` is True.

    Returns:
        An empty tuple when disabled, else the command as a tuple.
    """
    if value is False:
        return ()
    if value is True:
        return (tool,)
    return tuple(value)


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


def _resolve_python_version(version: str | None, *, name: str, script: str) -> str:
    """Validate a python_version= override, or fall back to the floor.

    Args:
        version: The user-supplied "MAJOR.MINOR" string, or None to use
            CMakeless's own supported floor.
        name: The owning Python module's name, for error messages.
        script: Display name of the owning build description, for messages.

    Returns:
        The version unchanged, or MIN_PYTHON_VERSION when None.

    Raises:
        ConfigurationError: When ``version`` is not two dot-separated
            non-negative integers.
    """
    if version is None:
        return MIN_PYTHON_VERSION
    parts = version.split(".")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        raise ConfigurationError(
            f"python_version={version!r} for Python module {name!r} in {script} "
            f"is not a valid 'MAJOR.MINOR' version, for example \"3.12\"."
        )
    return version
