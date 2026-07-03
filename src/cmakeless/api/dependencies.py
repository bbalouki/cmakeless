"""The Dependency class and the project-level dependency collection.

Users rarely construct a Dependency by hand; target.depends("fmt/10.2.1")
creates one and registers it here. The collection dedupes by package name,
rejects conflicting versions immediately, and owns the lockfile refresh.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from cmakeless._constants import BUILD_SCRIPT_NAME
from cmakeless.deps.find_package import fill_metadata
from cmakeless.deps.lockfile import LOCKFILE_NAME
from cmakeless.deps.resolver import resolve_dependencies
from cmakeless.errors import ConfigurationError
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
        resolve_dependencies(model, lock_path=lock_path, force=True)
        return lock_path

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
