"""The Project facade: the root object users interact with.

project.build() hides freeze, validate, emit, configure, and compile behind
one verb.
"""

from __future__ import annotations

import inspect
from collections.abc import Sequence
from pathlib import Path

from cmakeless._version import __version__
from cmakeless.api.targets import Executable
from cmakeless.driver import CMakeDriver
from cmakeless.emitter import emit_cmakelists
from cmakeless.model.nodes import ProjectModel
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
        root: str | Path | None = None,
    ) -> None:
        self._name = name
        self._version = version
        self._cpp_std = cpp_std
        script = _calling_script()
        if root is not None:
            self._root = Path(root).resolve()
        elif script is not None:
            self._root = script.parent
        else:
            self._root = Path.cwd()
        self._source_script = script.name if script is not None else "build.py"
        self._executables: list[Executable] = []

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
        """Declare a runnable target built from the given source files."""
        executable = Executable(name, sources)
        self._executables.append(executable)
        return executable

    def freeze(self) -> ProjectModel:
        """Freeze the mutable description into the validated, immutable model."""
        model = ProjectModel(
            name=self._name,
            version=self._version,
            cpp_std=self._cpp_std,
            root_dir=self._root,
            source_script=self._source_script,
            executables=tuple(target._freeze() for target in self._executables),
        )
        validate_project(model)
        return model

    def generate(self) -> Path:
        """Emit CMakeLists.txt without invoking CMake; returns the written path.

        Generation never requires CMake to be installed.
        """
        model = self.freeze()
        text = emit_cmakelists(model, tool_version=__version__)
        cmakelists = self._root / "CMakeLists.txt"
        cmakelists.write_text(text, encoding="utf-8", newline="\n")
        return cmakelists

    def configure(self) -> None:
        """Generate build files and run the CMake configure step."""
        self.generate()
        self._driver().configure()

    def build(self) -> None:
        """Freeze, validate, emit, configure, and compile: the whole pipeline."""
        self.configure()
        self._driver().build()

    def _driver(self) -> CMakeDriver:
        return CMakeDriver(
            source_dir=self._root,
            build_dir=self._root / DEFAULT_BUILD_DIR_NAME,
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
