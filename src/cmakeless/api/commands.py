# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Custom build steps: Command and CustomTarget, created via Project.

A Command is a build-time step that produces files other targets or
commands consume; a CustomTarget is an always-runnable named target with no
file output (asset cooking, lint, docs).
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from cmakeless.errors import ConfigurationError
from cmakeless.model.nodes import CommandModel, CustomTargetModel


class Command:
    """A build-time step; add_sources()/depends= on its output wires the edge.

    Attributes:
        outputs: The files this command produces, project-root-relative
            (read-only property).
    """

    def __init__(
        self,
        *,
        output: Sequence[str],
        command: Sequence[str],
        depends: Sequence[str | Command] = (),
        comment: str | None,
        script: str,
    ) -> None:
        """Describe a build-time step.

        Args:
            output: Files this command produces, project-root-relative.
            command: The argument vector to run; never a shell string.
            depends: Files (or other Command handles) that trigger a re-run.
            comment: Shown while the command runs, or None.
            script: Display name of the owning build description, used in
                error messages.

        Raises:
            ConfigurationError: When ``output`` or ``command`` is empty.
        """
        if not output:
            raise ConfigurationError(
                f"add_command() in {script} needs at least one output=..., "
                f"naming the file(s) it produces."
            )
        if not command:
            raise ConfigurationError(
                f"add_command() in {script} needs a non-empty command=[...] to run."
            )
        self._outputs = tuple(output)
        self._command = tuple(command)
        self._depends_raw = tuple(depends)
        self._comment = comment

    @property
    def outputs(self) -> tuple[str, ...]:
        """The files this command produces, project-root-relative."""
        return self._outputs

    def __repr__(self) -> str:
        """Developer-facing representation.

        Returns:
            The outputs and command of this build step.
        """
        return f"Command(output={list(self._outputs)!r}, command={list(self._command)!r})"

    def _freeze(self) -> CommandModel:
        """Freeze this builder into its immutable model node.

        Returns:
            The CommandModel; validation happens on the frozen project.
        """
        return CommandModel(
            outputs=tuple(Path(output) for output in self._outputs),
            command=self._command,
            depends=_freeze_depends(self._depends_raw),
            comment=self._comment,
        )


class CustomTarget:
    """An always-runnable named target with no file output.

    Attributes:
        name: The CMake target name (read-only property).
    """

    def __init__(
        self,
        name: str,
        *,
        command: Sequence[str],
        depends: Sequence[str | Command] = (),
        script: str,
    ) -> None:
        """Describe an always-run target.

        Args:
            name: The CMake target name; shares the project's target
                namespace.
            command: The argument vector to run.
            depends: Files (or Command handles) that must be up to date
                first.
            script: Display name of the owning build description, used in
                error messages.

        Raises:
            ConfigurationError: When ``command`` is empty.
        """
        if not command:
            raise ConfigurationError(
                f"add_custom_target({name!r}) in {script} needs a non-empty command=[...] to run."
            )
        self._name = name
        self._command = tuple(command)
        self._depends_raw = tuple(depends)

    @property
    def name(self) -> str:
        """The CMake target name."""
        return self._name

    def __repr__(self) -> str:
        """Developer-facing representation.

        Returns:
            The name and command of this custom target.
        """
        return f"CustomTarget(name={self._name!r}, command={list(self._command)!r})"

    def _freeze(self) -> CustomTargetModel:
        """Freeze this builder into its immutable model node.

        Returns:
            The CustomTargetModel; validation happens on the frozen project.
        """
        return CustomTargetModel(
            name=self._name,
            command=self._command,
            depends=_freeze_depends(self._depends_raw),
        )


def _freeze_depends(depends: Sequence[str | Command]) -> tuple[Path, ...]:
    """Flatten a depends= list: plain paths stay, Command handles expand.

    Args:
        depends: Plain path strings and/or Command handles.

    Returns:
        Project-root-relative paths: literal entries as given, and every
        Command handle expanded to its declared outputs.
    """
    resolved: list[Path] = []
    for entry in depends:
        if isinstance(entry, Command):
            resolved.extend(Path(output) for output in entry.outputs)
        else:
            resolved.append(Path(entry))
    return tuple(resolved)
