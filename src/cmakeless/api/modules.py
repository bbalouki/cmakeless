# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""CMakeModule: a reflected include(), created via Project.include()/.include_module().

Reflection runs real CMake immediately when Project.include()/.include_module()
is called (never a hand-written CMake-language parser), so mod.call(...) can
validate against the module's real discovered functions before any
CMakeLists.txt is emitted.
"""

from __future__ import annotations

from pathlib import Path

from cmakeless.driver.reflection import ModuleReflection
from cmakeless.errors import ConfigurationError
from cmakeless.model.nodes import ModuleCallModel, ModuleKind, ModuleModel


class CMakeModule:
    """A reflected CMake include: its discovered functions, variables, and targets.

    Not constructed directly: returned by Project.include() and
    Project.include_module().

    Attributes:
        functions: Function/macro names the include newly defined
            (read-only property).
        variables: Variable names the include newly defined (read-only
            property).
        targets: Target names the include defined, discovered best-effort
            (read-only property; empty when the throwaway target probe
            could not configure).
    """

    def __init__(
        self,
        *,
        kind: ModuleKind,
        reference: str,
        module_path: Path | None,
        reflection: ModuleReflection,
        script: str,
    ) -> None:
        """Wrap one already-reflected include.

        Args:
            kind: FILE (a path) or NAMED (a bare module name).
            reference: The path (FILE, POSIX-normalized) or module name
                (NAMED), exactly as it will be emitted.
            module_path: An extra CMAKE_MODULE_PATH entry for NAMED
                includes, project-root-relative, or None.
            reflection: The functions/variables/targets CMake itself
                reported for this include.
            script: Display name of the owning build description, used in
                error messages.
        """
        self._kind = kind
        self._reference = reference
        self._module_path = module_path
        self._reflection = reflection
        self._script = script
        self._calls: list[tuple[str, tuple[str, ...]]] = []

    @property
    def functions(self) -> tuple[str, ...]:
        """Function/macro names this include newly defined."""
        return self._reflection.functions

    @property
    def variables(self) -> tuple[str, ...]:
        """Variable names this include newly defined."""
        return self._reflection.variables

    @property
    def targets(self) -> tuple[str, ...]:
        """Target names this include defined, discovered best-effort."""
        return self._reflection.targets

    def call(self, function: str, *args: str) -> None:
        """Call a discovered function or macro, validated against reflection.

        Args:
            function: The function or macro name; matched case-insensitively,
                since CMake function and macro names are.
            *args: Positional arguments, emitted verbatim in the generated
                CMakeLists.txt, in the order given.

        Raises:
            ConfigurationError: When ``function`` is not one this include
                defined.
        """
        known = {name.lower(): name for name in self._reflection.functions}
        canonical = known.get(function.lower())
        if canonical is None:
            available = ", ".join(sorted(self._reflection.functions)) or "none"
            raise ConfigurationError(
                f"{self._reference!r} in {self._script} has no function or "
                f"macro named {function!r}. Available: {available}."
            )
        self._calls.append((canonical, tuple(args)))

    def variable(self, name: str) -> str:
        """Read one discovered variable's resolved value.

        Args:
            name: The variable name; matched exactly (CMake variable names
                are case-sensitive).

        Returns:
            The variable's value, as CMake resolved it during reflection.

        Raises:
            ConfigurationError: When ``name`` is not one this include
                defined.
        """
        if name not in self._reflection.variable_values:
            available = ", ".join(sorted(self._reflection.variables)) or "none"
            raise ConfigurationError(
                f"{self._reference!r} in {self._script} has no variable "
                f"named {name!r}. Available: {available}."
            )
        return self._reflection.variable_values[name]

    def __repr__(self) -> str:
        """Developer-facing representation.

        Returns:
            The kind and reference of this include.
        """
        return f"CMakeModule(kind={self._kind.value!r}, reference={self._reference!r})"

    def _freeze(self) -> ModuleModel:
        """Freeze this builder into its immutable model node.

        Returns:
            The ModuleModel; calls are kept in declaration order (validation
            of the reference path itself happens on the frozen project).
        """
        return ModuleModel(
            kind=self._kind,
            reference=self._reference,
            module_path=self._module_path,
            calls=tuple(ModuleCallModel(function=name, args=args) for name, args in self._calls),
        )


def check_file_reference(path: Path, *, root: Path, script: str) -> None:
    """Eagerly check a project.include() path, before reflection ever runs.

    Reflection runs real CMake immediately, so a missing file would
    otherwise surface as a raw CMake error instead of CMakeless's own
    what/where/next-step message.

    Args:
        path: The path as passed to project.include().
        root: The project root directory.
        script: Display name of the owning build description.

    Raises:
        ConfigurationError: When the path is absolute, escapes the root, or
            does not exist.
    """
    # anchor catches a leading '/' even on Windows, where is_absolute()
    # needs a drive letter and would miss "/etc/evil.cmake".
    if path.anchor or path.is_absolute() or ".." in path.parts:
        raise ConfigurationError(
            f"project.include() path '{path.as_posix()}' in {script} must be "
            f"a relative path inside the project root. Move the file under "
            f"the root, or pass a path relative to it."
        )
    resolved = root / path
    if not resolved.is_file():
        raise ConfigurationError(
            f"project.include() path '{path.as_posix()}' in {script} does "
            f"not exist (looked for {resolved}). Create the file, or fix "
            f"the path."
        )


def check_module_path(directory: Path, *, root: Path, script: str) -> None:
    """Eagerly check a project.include_module(module_path=...) directory.

    Args:
        directory: The directory as passed to include_module().
        root: The project root directory.
        script: Display name of the owning build description.

    Raises:
        ConfigurationError: When the directory is absolute, escapes the
            root, or does not exist.
    """
    if directory.anchor or directory.is_absolute() or ".." in directory.parts:
        raise ConfigurationError(
            f"project.include_module() module_path '{directory.as_posix()}' "
            f"in {script} must be a relative path inside the project root. "
            f"Move the directory under the root, or pass a path relative to it."
        )
    resolved = root / directory
    if not resolved.is_dir():
        raise ConfigurationError(
            f"project.include_module() module_path '{directory.as_posix()}' "
            f"in {script} does not exist (looked for {resolved}). Create "
            f"the directory, or fix the path."
        )
