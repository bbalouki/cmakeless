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
from cmakeless.api.targets import Executable, Library, LibraryKindName
from cmakeless.driver import CMakeDriver, select_generator
from cmakeless.emitter import emit_tree
from cmakeless.errors import ConfigurationError
from cmakeless.model.nodes import ProjectModel, SubprojectModel
from cmakeless.model.validate import validate_project

DEFAULT_BUILD_DIR_NAME = "build"


class Project:
    """The root build description and the facade over the whole pipeline."""

    def __init__(
        self,
        name: str,
        *,
        version: str = "0.1.0",
        cpp_std: int = 17,
        warnings: str = "default",
        root: str | Path | None = None,
    ) -> None:
        self._name = name
        self._version = version
        self._cpp_std = cpp_std
        self.warnings = warnings
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
        self._generator: str | None = None
        _context.register_project(self)

    @property
    def name(self) -> str:
        return self._name

    @property
    def root(self) -> Path:
        return self._root

    def __repr__(self) -> str:
        return (
            f"Project(name={self._name!r}, version={self._version!r}, "
            f"cpp_std={self._cpp_std}, root={str(self._root)!r})"
        )

    def add_executable(self, name: str, sources: Sequence[str]) -> Executable:
        """Declare a runnable target built from the given source files or globs."""
        executable = Executable(name, sources, script=self._source_script)
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
        """Declare a library target ("static", "shared", or "header_only")."""
        library = Library(
            name,
            sources,
            public_headers=public_headers,
            kind=kind,
            script=self._source_script,
        )
        self._libraries.append(library)
        return library

    def add_subproject(self, path: str | Path) -> Project:
        """Mount a self-contained child project (its own build.py) at a
        directory relative to this project's root."""
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
        """Freeze the mutable description into the validated, immutable model."""
        model = self._freeze_without_validation()
        validate_project(model)
        return model

    def generate(self) -> list[Path]:
        """Emit all CMakeLists.txt files without invoking CMake; returns the
        written paths (parent first).

        Generation never requires CMake to be installed.
        """
        model = self.freeze()
        written: list[Path] = []
        for relative_path, text in emit_tree(model, tool_version=__version__).items():
            output = self._root / relative_path
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(text, encoding="utf-8", newline="\n")
            written.append(output)
        return written

    def configure(self) -> None:
        """Generate build files and run the CMake configure step."""
        self.generate()
        self._driver().configure()

    def clean(self) -> None:
        """Delete this project's build directory."""
        build_dir = self._root / DEFAULT_BUILD_DIR_NAME
        if build_dir.is_dir():
            shutil.rmtree(build_dir)
            print(f"[cmakeless] Removed {build_dir}")

    def build(self) -> None:
        """Freeze, validate, emit, configure, and compile: the whole pipeline.

        Under the cmakeless CLI this dispatches to the verb the user asked for,
        so one build.py serves 'cmakeless build', 'configure', and 'clean'.
        In description mode (this project is being loaded as a subproject) it
        does nothing: the parent owns the pipeline.
        """
        if _context.in_description_mode():
            return
        verb = _context.active_verb()
        if verb == "clean":
            self.clean()
        elif verb == "configure":
            self.configure()
        else:
            self.configure()
            self._driver().build()

    def set_generator(self, generator: str | None) -> None:
        """Choose the CMake generator ("ninja", "vs", or a raw -G string)."""
        self._generator = generator

    def _freeze_without_validation(self) -> ProjectModel:
        return ProjectModel(
            name=self._name,
            version=self._version,
            cpp_std=self._cpp_std,
            root_dir=self._root,
            source_script=self._source_script,
            warnings=self.warnings,
            executables=tuple(target._freeze(self._root) for target in self._executables),
            libraries=tuple(target._freeze(self._root) for target in self._libraries),
            subprojects=tuple(
                SubprojectModel(directory=directory, project=child._freeze_without_validation())
                for directory, child in self._subprojects
            ),
        )

    def _driver(self) -> CMakeDriver:
        return CMakeDriver(
            source_dir=self._root,
            build_dir=self._root / DEFAULT_BUILD_DIR_NAME,
            generator=select_generator(self._generator or _context.active_generator()),
        )


def _calling_script() -> Path | None:
    """Find the user's script (usually build.py) that invoked the cmakeless API.

    Walking the stack keeps Project's root defaulting to the directory of the
    build description, not the process working directory, so 'python
    somewhere/build.py' behaves identically to 'cmakeless build' run inside it.
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
