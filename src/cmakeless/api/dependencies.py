# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""The Dependency class and the project-level dependency collection.

Users rarely construct a Dependency by hand; target.depends("fmt/10.2.1")
creates one and registers it here. The collection dedupes by package name,
rejects conflicting versions immediately, and owns the lockfile refresh.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from cmakeless._constants import BUILD_SCRIPT_NAME
from cmakeless.api import _context
from cmakeless.deps.find_package import fill_metadata
from cmakeless.deps.lockfile import LOCKFILE_NAME, read_lockfile
from cmakeless.deps.resolver import resolve_dependencies
from cmakeless.deps.sbom import SBOM_FORMATS, generate_cyclonedx, generate_spdx
from cmakeless.deps.vendor import vendor_packages
from cmakeless.errors import ConfigurationError, DependencyError
from cmakeless.model.nodes import DependencyModel

if TYPE_CHECKING:
    from cmakeless.api.project import Project


class Dependency:
    """One external package requirement, usually created by target.depends().

    Attributes:
        name: The package name (read-only property).
        version: The required version (read-only property).
    """

    def __init__(
        self,
        spec: str,
        *,
        components: Sequence[str] = (),
        url: str | None = None,
        sha256: str | None = None,
        cmake_name: str | None = None,
        targets: Sequence[str] = (),
        script: str = BUILD_SCRIPT_NAME,
    ) -> None:
        """Describe an external package requirement.

        Args:
            spec: The package as "name/version", for example "fmt/10.2.1".
            components: Package components, for example Boost's "asio".
            url: Source archive URL, overriding the built-in registry.
            sha256: Archive pin to verify the download against.
            cmake_name: The find_package() name, overriding the registry.
            targets: Imported target names consumers link, overriding the
                registry (for example ["fmt::fmt"]).
            script: Display name of the owning build description, used in
                error messages.

        Raises:
            ConfigurationError: When the spec is malformed.
            DependencyError: When neither the registry nor the overrides
                say what CMake should see for this package.
        """
        name, version = _parse_spec(spec, script=script)
        self._script = script
        # Metadata is resolved eagerly, so a typo fails at the depends()
        # call site with the user's own line in the traceback.
        self._model = fill_metadata(
            DependencyModel(
                name=name,
                version=version,
                components=tuple(components),
                cmake_name=cmake_name,
                link_targets=tuple(targets),
                url=url,
                sha256=sha256,
            )
        )

    @property
    def name(self) -> str:
        """The package name, the part left of '/' in the spec."""
        return self._model.name

    @property
    def version(self) -> str:
        """The required version, the part right of '/' in the spec."""
        return self._model.version

    def __repr__(self) -> str:
        """Developer-facing representation.

        Returns:
            The spec and imported targets of this dependency.
        """
        return (
            f"Dependency(spec={self.name + '/' + self.version!r}, "
            f"targets={list(self._model.link_targets)!r})"
        )

    def _freeze(self) -> DependencyModel:
        """Hand out the frozen model node, metadata already filled.

        Returns:
            The DependencyModel; the resolver fills fetch pins later.
        """
        return self._model

    def _link_targets(self) -> tuple[str, ...]:
        """The imported targets a depending target must link.

        Returns:
            One or more target names like "fmt::fmt".
        """
        return self._model.link_targets


class Dependencies:
    """The project-level dependency collection, exposed as project.dependencies."""

    def __init__(self, project: Project) -> None:
        """Bind the collection to its owning project.

        Args:
            project: The project whose targets register dependencies here.
        """
        self._project = project
        self._by_name: dict[str, Dependency] = {}

    def __iter__(self) -> Iterator[Dependency]:
        """Iterate the registered dependencies in name order.

        Returns:
            An iterator over the dependencies, sorted by package name.
        """
        return iter(self._by_name[name] for name in sorted(self._by_name))

    def __len__(self) -> int:
        """Count the registered dependencies.

        Returns:
            The number of distinct packages.
        """
        return len(self._by_name)

    def __repr__(self) -> str:
        """Developer-facing representation.

        Returns:
            The registered package specs, sorted by name.
        """
        specs = [f"{dep.name}/{dep.version}" for dep in self]
        return f"Dependencies({specs!r})"

    def add(
        self,
        spec: str,
        *,
        components: Sequence[str] = (),
        url: str | None = None,
        sha256: str | None = None,
        cmake_name: str | None = None,
        targets: Sequence[str] = (),
    ) -> Dependency:
        """Register a package requirement, deduplicating by name.

        Args:
            spec: The package as "name/version", for example "fmt/10.2.1".
            components: Package components, for example Boost's "asio".
            url: Source archive URL, overriding the built-in registry.
            sha256: Archive pin to verify the download against.
            cmake_name: The find_package() name, overriding the registry.
            targets: Imported target names, overriding the registry.

        Returns:
            The registered Dependency; an identical repeat spec returns the
            existing one.

        Raises:
            ConfigurationError: When the spec is malformed or conflicts
                with an earlier depends() call for the same package.
            DependencyError: When the package cannot be described.
        """
        dependency = Dependency(
            spec,
            components=components,
            url=url,
            sha256=sha256,
            cmake_name=cmake_name,
            targets=targets,
            script=self._project._source_script,
        )
        existing = self._by_name.get(dependency.name)
        if existing is None:
            self._by_name[dependency.name] = dependency
            return dependency
        if existing._freeze() != dependency._freeze():
            raise _conflict_error(existing, dependency, self._project._source_script)
        return existing

    def lock(self) -> Path:
        """Refresh cmakeless.lock: re-resolve every pin, ignoring old entries.

        Returns:
            The lockfile path; the file is only (re)written when the
            project tree has at least one dependency.

        Raises:
            ConfigurationError: When the build description is invalid.
            DependencyError: When a package cannot be resolved.
        """
        model = self._project.freeze()
        lock_path = self._project.root / LOCKFILE_NAME
        resolve_dependencies(
            model, lock_path=lock_path, force=True, offline=_context.active_offline()
        )
        return lock_path

    def sbom(self, *, format: str = "cyclonedx", output: str | Path | None = None) -> Path:
        """Write a CycloneDX or SPDX bill of materials from cmakeless.lock.

        Reads the already-resolved lockfile rather than re-resolving
        dependencies, so it needs no network and reflects exactly what a
        prior 'cmakeless lock' pinned.

        Args:
            format: "cyclonedx" (the default) or "spdx".
            output: The file to write, or None for
                "<project name>.cdx.json"/"<project name>.spdx.json" in the
                project root.

        Returns:
            The written file's path.

        Raises:
            ConfigurationError: When ``format`` is not a known one.
            DependencyError: When no cmakeless.lock exists yet.
        """
        if format not in SBOM_FORMATS:
            known = ", ".join(repr(name) for name in sorted(SBOM_FORMATS))
            raise ConfigurationError(f"Unknown SBOM format {format!r}. Pick one of: {known}.")
        lock_path = self._project.root / LOCKFILE_NAME
        if not lock_path.is_file():
            raise DependencyError(
                f"No {LOCKFILE_NAME} found at {lock_path}. Run `cmakeless lock` "
                f"first to resolve dependencies before generating a bill of "
                f"materials."
            )
        lock = read_lockfile(lock_path)
        if format == "cyclonedx":
            document = generate_cyclonedx(
                lock, project_name=self._project.name, project_version=self._project._version
            )
            suffix = "cdx.json"
        else:
            document = generate_spdx(
                lock, project_name=self._project.name, project_version=self._project._version
            )
            suffix = "spdx.json"
        out_path = (
            Path(output)
            if output is not None
            else self._project.root / f"{self._project.name}.{suffix}"
        )
        out_path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return out_path

    def vendor(self, *, directory: str | Path | None = None) -> Path:
        """Download every locked dependency's archive for zero-network builds.

        Also writes cmakeless.mirror.json so a later --offline build
        resolves each vendored package from the local copy automatically.

        Args:
            directory: Where to download archives, or None for "vendor" in
                the project root.

        Returns:
            The vendor directory.

        Raises:
            DependencyError: When no cmakeless.lock exists yet, a download
                fails, or a downloaded archive's hash does not match its
                locked pin.
        """
        lock_path = self._project.root / LOCKFILE_NAME
        if not lock_path.is_file():
            raise DependencyError(
                f"No {LOCKFILE_NAME} found at {lock_path}. Run `cmakeless lock` "
                f"first to resolve dependencies before vendoring them."
            )
        lock = read_lockfile(lock_path)
        vendor_dir = Path(directory) if directory is not None else self._project.root / "vendor"
        vendor_packages(lock, directory=vendor_dir, root_dir=self._project.root)
        return vendor_dir

    def _freeze(self) -> tuple[DependencyModel, ...]:
        """Freeze the collection into model nodes, sorted by name.

        Returns:
            One DependencyModel per registered package.
        """
        return tuple(dependency._freeze() for dependency in self)


def _parse_spec(spec: str, *, script: str) -> tuple[str, str]:
    """Split a "name/version" spec into its parts.

    Args:
        spec: The user-supplied spec string.
        script: Display name of the build description, for error messages.

    Returns:
        The (name, version) pair.

    Raises:
        ConfigurationError: When the spec is not exactly "name/version".
    """
    name, separator, version = spec.partition("/")
    if not separator or not name or not version or "/" in version:
        raise ConfigurationError(
            f'Dependency spec {spec!r} in {script} must be "name/version", for '
            f'example depends("fmt/10.2.1").'
        )
    return (name, version)


def _conflict_error(existing: Dependency, new: Dependency, script: str) -> ConfigurationError:
    """Build the error for two conflicting descriptions of one package.

    Args:
        existing: The dependency registered first.
        new: The conflicting newcomer.
        script: Display name of the build description, for the message.

    Returns:
        The ready-to-raise error naming both descriptions.
    """
    if existing.version != new.version:
        detail = f"it is already required as {existing.name}/{existing.version}"
    else:
        detail = "it is already required with different components or overrides"
    return ConfigurationError(
        f"Cannot require {new.name}/{new.version} in {script}: {detail}. Use one "
        f"consistent depends() description per package across the project."
    )
