"""Workspaces: several CMakeless projects in one repository, one lockfile.

A cmakelessworkspace.py at the repository root lists the projects; every
verb runs across them with one shared cmakeless.lock, so the whole
repository agrees on one version of every dependency.
"""

from __future__ import annotations

import runpy
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from cmakeless._constants import BUILD_SCRIPT_NAME
from cmakeless.api import _context
from cmakeless.api._callsite import calling_frame
from cmakeless.errors import ConfigurationError

WORKSPACE_SCRIPT_NAME = "cmakelessworkspace.py"


class Workspace:
    """A set of projects built together against one shared lockfile."""

    def __init__(self, *, lockfile: str = "cmakeless.lock", root: str | Path | None = None) -> None:
        """Start describing a workspace.

        Args:
            lockfile: The shared lockfile, relative to the workspace root.
            root: The workspace root; defaults to the directory of the
                script that constructed the Workspace.
        """
        frame = calling_frame()
        if root is not None:
            self._root = Path(root).resolve()
        else:
            self._root = frame[0].parent if frame is not None else Path.cwd()
        self._lockfile = self._root / lockfile
        self._projects: list[tuple[Path, tuple[str, ...]]] = []

    @property
    def root(self) -> Path:
        """The workspace root directory."""
        return self._root

    @property
    def projects(self) -> tuple[Path, ...]:
        """The member project directories, relative to the root, in order."""
        return tuple(directory for directory, _ in self._projects)

    def add(self, directory: str, *, presets: Sequence[str] = ()) -> None:
        """Add a member project.

        Args:
            directory: The project directory, relative to the workspace root;
                it must contain a cmakelessfile.py.
            presets: The presets 'cmakeless matrix' builds for this member;
                empty for all of them.

        Raises:
            ConfigurationError: When the directory has no build description.
        """
        path = Path(directory)
        if not (self._root / path / BUILD_SCRIPT_NAME).is_file():
            raise ConfigurationError(
                f"Workspace member '{path.as_posix()}' has no {BUILD_SCRIPT_NAME} "
                f"(looked in {self._root / path}). Create one, or fix the path."
            )
        self._projects.append((path, tuple(presets)))

    def build(self) -> None:
        """Run the CLI's verb across the selected members, one after another.

        'cmakeless <verb> --project NAME' selects one member by directory
        name, and '--affected-since REF' selects the members whose files
        changed since a git revision.

        Raises:
            ConfigurationError: When the selection matches no member.
        """
        options = _context.active_run_options()
        selected = self.select(
            project=options.workspace_project, affected_since=options.affected_since
        )
        presets_by_member = dict(self._projects)
        with _context.lock_path_override(self._lockfile):
            for directory in selected:
                member = replace(options, presets=options.presets or presets_by_member[directory])
                script = self._root / directory / BUILD_SCRIPT_NAME
                print(f"[cmakeless] workspace: {directory.as_posix()}")
                with _context.run_options_override(member):
                    runpy.run_path(str(script), run_name="__main__")

    def select(
        self, *, project: str | None = None, affected_since: str | None = None
    ) -> list[Path]:
        """Choose which members a run covers.

        Args:
            project: A member's directory name or path, or None for all.
            affected_since: A git revision; only members with changes since
                it are kept. A change to the shared lockfile or the
                workspace description affects every member.

        Returns:
            The selected member directories.

        Raises:
            ConfigurationError: When ``project`` matches no member.
        """
        members = list(self.projects)
        if project is not None:
            members = [m for m in members if project in (m.as_posix(), m.name)]
            if not members:
                known = ", ".join(m.as_posix() for m in self.projects)
                raise ConfigurationError(
                    f"No workspace member named {project!r}; members: {known}."
                )
        if affected_since is None:
            return members
        changed = self._changed_files(affected_since)
        shared = {WORKSPACE_SCRIPT_NAME, self._lockfile.relative_to(self._root).as_posix()}
        if changed & shared:
            return members
        return [m for m in members if any(c.startswith(m.as_posix() + "/") for c in changed)]

    def _changed_files(self, revision: str) -> set[str]:
        """List the files changed since a revision, committed or not.

        Args:
            revision: A git revision, for example "origin/main".

        Returns:
            Root-relative POSIX paths.

        Raises:
            ConfigurationError: When git is unavailable or the revision is unknown.
        """
        git = shutil.which("git")
        if git is None:
            raise ConfigurationError("--affected-since needs git on PATH.")
        completed = subprocess.run(
            [git, "diff", "--name-only", revision],
            capture_output=True,
            text=True,
            check=False,
            cwd=self._root,
        )
        if completed.returncode != 0:
            raise ConfigurationError(
                f"git could not diff against {revision!r}: {completed.stderr.strip()}"
            )
        return {line.strip() for line in completed.stdout.splitlines() if line.strip()}

    def __repr__(self) -> str:
        """Developer-facing representation.

        Returns:
            The root and member directories.
        """
        members = [directory.as_posix() for directory in self.projects]
        return f"Workspace(root={str(self._root)!r}, projects={members!r})"
