"""The Project facade: the root object users interact with.

project.build() hides freeze, validate, emit, configure, and compile behind
one verb.
"""

from __future__ import annotations

import inspect
import runpy
import shutil
from collections.abc import Sequence
from pathlib import Path

from cmakeless._version import __version__
from cmakeless.api import _context
from cmakeless.api.dependencies import Dependencies
from cmakeless.api.targets import Executable, Library, LibraryKindName
from cmakeless.deps import (
    LOCKFILE_NAME,
    DependencyProvider,
    collect_tree_dependencies,
    provider_for,
    read_lockfile,
    resolve_dependencies,
)
from cmakeless.driver import CMakeDriver, select_generator
from cmakeless.emitter import emit_tree
from cmakeless.errors import ConfigurationError
from cmakeless.model.nodes import ProjectModel, SubprojectModel
from cmakeless.model.validate import validate_project

DEFAULT_BUILD_DIR_NAME = "build"


class Project:
    """The root build description and the facade over the whole pipeline.

    Attributes:
        warnings: Warning preset name ("strict", "default", or "none");
            plain attribute, assign to change it.
        package_manager: Dependency strategy ("auto", "find_package",
            "vcpkg", or "conan"); plain attribute, assign to change it.
        name: The project name (read-only property).
        root: Absolute project root directory (read-only property).
        dependencies: The project's dependency collection (read-only
            property).
    """

    def __init__(
        self,
        name: str,
        *,
        version: str = "0.1.0",
        cpp_std: int = 17,
        warnings: str = "default",
        root: str | Path | None = None,
    ) -> None:
        """Start describing a project.

        Args:
            name: The CMake project name.
            version: The project version string, passed to CMake.
            cpp_std: The C++ standard every target compiles with.
            warnings: Warning preset ("strict", "default", or "none").
            root: Project root directory; defaults to the directory of the
                script that constructed the Project (usually build.py).
        """
        self._name = name
        self._version = version
        self._cpp_std = cpp_std
        self.warnings = warnings
        self.package_manager = "auto"
        script = _calling_script()
        if root is not None:
            self._root = Path(root).resolve()
        elif script is not None:
            self._root = script.parent
        else:
            self._root = Path.cwd()
        self._source_script = script.name if script is not None else "build.py"
        self._executables: list[Executable] = []
        self._libraries: list[Library] = []
        self._subprojects: list[tuple[Path, Project]] = []
        self._dependencies = Dependencies(self)
        self._generator: str | None = None
        _context.register_project(self)

    @property
    def name(self) -> str:
        """The CMake project name."""
        return self._name

    @property
    def root(self) -> Path:
        """Absolute path of the project root directory."""
        return self._root

    @property
    def dependencies(self) -> Dependencies:
        """The project's dependency collection; supports .lock()."""
        return self._dependencies

    def __repr__(self) -> str:
        """Developer-facing representation.

        Returns:
            The name, version, C++ standard, and root of this project.
        """
        return (
            f"Project(name={self._name!r}, version={self._version!r}, "
            f"cpp_std={self._cpp_std}, root={str(self._root)!r})"
        )

    def add_executable(self, name: str, sources: Sequence[str]) -> Executable:
        """Declare a runnable target built from the given source files or globs.

        Args:
            name: Unique target name within the project.
            sources: Source files or glob patterns, project-root-relative.

        Returns:
            The mutable Executable builder, for further link()/define() calls.
        """
        executable = Executable(
            name, sources, script=self._source_script, dependencies=self._dependencies
        )
        self._executables.append(executable)
        return executable

    def add_library(
        self,
        name: str,
        sources: Sequence[str] = (),
        *,
        public_headers: str | Sequence[str] = (),
        kind: LibraryKindName = "static",
    ) -> Library:
        """Declare a library target.

        Args:
            name: Unique target name within the project.
            sources: Source files or glob patterns; empty for header-only.
            public_headers: Directory (or directories) whose headers
                consumers may include.
            kind: "static", "shared", or "header_only".

        Returns:
            The mutable Library builder, for further link()/define() calls.

        Raises:
            ConfigurationError: When ``kind`` is not a known library kind.
        """
        library = Library(
            name,
            sources,
            public_headers=public_headers,
            kind=kind,
            script=self._source_script,
            dependencies=self._dependencies,
        )
        self._libraries.append(library)
        return library

    def add_subproject(self, path: str | Path) -> Project:
        """Mount a self-contained child project at a directory under the root.

        The child directory must contain its own build.py describing exactly
        one Project; it is executed in description mode, so its own
        project.build() call registers the project instead of building.

        Args:
            path: Directory of the child project, relative to this root.

        Returns:
            The captured child Project.

        Raises:
            ConfigurationError: When the child has no build.py, describes a
                number of projects other than one, or closes a mount cycle.
        """
        directory = Path(path)
        script = self._root / directory / "build.py"
        if not script.is_file():
            raise ConfigurationError(
                f"Subproject '{directory.as_posix()}' added in {self._source_script} "
                f"has no build description (looked for {script}). Create a build.py "
                f"there, or fix the path."
            )
        with _context.loading_script(script), _context.capturing_projects() as captured:
            runpy.run_path(str(script))
        if len(captured) != 1:
            raise ConfigurationError(
                f"Subproject '{directory.as_posix()}' must describe exactly one "
                f"Project in its build.py, found {len(captured)}. Keep one Project "
                f"per build.py; split anything else into further subprojects."
            )
        child = captured[0]
        self._subprojects.append((directory, child))
        return child

    def freeze(self) -> ProjectModel:
        """Freeze the mutable description into the validated, immutable model.

        Returns:
            The validated ProjectModel, subprojects included.

        Raises:
            ConfigurationError: When the description is invalid.
        """
        model = self._freeze_without_validation()
        validate_project(model)
        return model

    def generate(self) -> list[Path]:
        """Emit all CMakeLists.txt files (and manifests) without invoking CMake.

        Generation never requires CMake to be installed. Dependencies are
        resolved first, which refreshes cmakeless.lock; with a complete
        lockfile this needs no network either.

        Returns:
            The written file paths, parent project first.

        Raises:
            ConfigurationError: When the description is invalid.
            DependencyError: When a package cannot be resolved.
        """
        return self._write_outputs(self._resolved_model())

    def configure(self) -> None:
        """Generate build files and run the CMake configure step.

        Raises:
            ConfigurationError: When the description is invalid.
            DependencyError: When a package cannot be resolved.
            ToolchainError: When cmake or the package manager is missing.
            CMakeError: When the configure step fails.
        """
        model = self._resolved_model()
        self._write_outputs(model)
        provider = self._provider(model)
        if provider is not None:
            provider.pre_configure(
                root_dir=self._root, build_dir=self._root / DEFAULT_BUILD_DIR_NAME
            )
        self._driver(provider).configure()

    def clean(self) -> None:
        """Delete this project's build directory, if it exists."""
        build_dir = self._root / DEFAULT_BUILD_DIR_NAME
        if build_dir.is_dir():
            shutil.rmtree(build_dir)
            print(f"[cmakeless] Removed {build_dir}")

    def build(self) -> None:
        """Freeze, validate, emit, configure, and compile: the whole pipeline.

        Under the cmakeless CLI this dispatches to the verb the user asked
        for, so one build.py serves 'cmakeless build', 'configure', 'clean',
        and 'lock'. In description mode (this project is being loaded as a
        subproject) it does nothing: the parent owns the pipeline.

        Raises:
            ConfigurationError: When the description is invalid.
            DependencyError: When a package cannot be resolved.
            ToolchainError: When cmake or the package manager is missing.
            CMakeError: When configuring or compiling fails.
        """
        if _context.in_description_mode():
            return
        verb = _context.active_verb()
        if verb == "clean":
            self.clean()
        elif verb == "configure":
            self.configure()
        elif verb == "lock":
            self._refresh_lock()
        else:
            self.configure()
            self._driver().build()

    def set_generator(self, generator: str | None) -> None:
        """Choose the CMake generator for this project's builds.

        Args:
            generator: "ninja", "vs", any raw CMake -G name, or None to
                auto-select (Ninja when available).
        """
        self._generator = generator

    def _freeze_without_validation(self) -> ProjectModel:
        """Freeze this project and its subprojects without validating.

        Validation runs once, at the top of the tree, in freeze().

        Returns:
            The frozen but not yet validated ProjectModel.
        """
        return ProjectModel(
            name=self._name,
            version=self._version,
            cpp_std=self._cpp_std,
            root_dir=self._root,
            source_script=self._source_script,
            warnings=self.warnings,
            package_manager=self.package_manager,
            executables=tuple(target._freeze(self._root) for target in self._executables),
            libraries=tuple(target._freeze(self._root) for target in self._libraries),
            dependencies=self._dependencies._freeze(),
            subprojects=tuple(
                SubprojectModel(directory=directory, project=child._freeze_without_validation())
                for directory, child in self._subprojects
            ),
        )

    def _resolved_model(self) -> ProjectModel:
        """Freeze, validate, and resolve dependencies into a complete model.

        Returns:
            The model with every dependency pin filled; resolution also
            refreshes cmakeless.lock when the tree has dependencies.
        """
        return resolve_dependencies(self.freeze(), lock_path=self._root / LOCKFILE_NAME)

    def _write_outputs(self, model: ProjectModel) -> list[Path]:
        """Write the emitted CMake tree and any backend manifest files.

        Args:
            model: The resolved project model.

        Returns:
            The written file paths, parent project first.
        """
        files = emit_tree(model, tool_version=__version__)
        provider = self._provider(model)
        if provider is not None:
            files.update(provider.manifest_files(model, read_lockfile(self._root / LOCKFILE_NAME)))
        written: list[Path] = []
        for relative_path, text in files.items():
            output = self._root / relative_path
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(text, encoding="utf-8", newline="\n")
            written.append(output)
        return written

    def _provider(self, model: ProjectModel) -> DependencyProvider | None:
        """Select the dependency provider, when the tree has dependencies.

        Args:
            model: The frozen project model.

        Returns:
            The backend adapter, or None for a dependency-free tree.
        """
        if not collect_tree_dependencies(model):
            return None
        return provider_for(model.package_manager)

    def _refresh_lock(self) -> None:
        """Perform the 'lock' verb: refresh every pin in cmakeless.lock."""
        lock_path = self._dependencies.lock()
        if lock_path.is_file():
            print(f"[cmakeless] Dependency pins refreshed in {lock_path}")
        else:
            print("[cmakeless] No dependencies to lock; nothing written.")

    def _driver(self, provider: DependencyProvider | None = None) -> CMakeDriver:
        """Build the driver for this project's source and build directories.

        Args:
            provider: The dependency backend whose toolchain arguments the
                configure step needs, or None for a dependency-free tree.

        Returns:
            A CMakeDriver honoring the project's or CLI's generator choice.
        """
        build_dir = self._root / DEFAULT_BUILD_DIR_NAME
        extra = provider.toolchain_args(build_dir) if provider is not None else ()
        return CMakeDriver(
            source_dir=self._root,
            build_dir=build_dir,
            generator=select_generator(self._generator or _context.active_generator()),
            extra_configure_args=extra,
        )


def _calling_script() -> Path | None:
    """Find the user's script (usually build.py) that invoked the cmakeless API.

    Walking the stack keeps Project's root defaulting to the directory of the
    build description, not the process working directory, so 'python
    somewhere/build.py' behaves identically to 'cmakeless build' run inside it.

    Returns:
        Absolute path of the first stack frame outside the cmakeless
        package, or None when every frame is internal (REPL, embedding).
    """
    package_root = Path(__file__).resolve().parent.parent
    for frame_info in inspect.stack():
        filename = frame_info.filename
        if not filename or filename.startswith("<"):
            continue
        candidate = Path(filename).resolve()
        if not candidate.is_relative_to(package_root):
            return candidate
    return None
