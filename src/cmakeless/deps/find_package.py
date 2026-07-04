# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""The find_package adapter: system packages, version-checked by CMake.

This adapter fills in metadata only (the find_package name and the imported
targets); the version check itself is delegated to CMake, which receives the
required version in the emitted find_package() call.
"""

from __future__ import annotations

from dataclasses import replace

from cmakeless.deps.provider import DependencyProvider, ResolutionContext
from cmakeless.deps.registry import known_packages, registry_entry
from cmakeless.errors import DependencyError
from cmakeless.model.nodes import DependencyModel


class FindPackageAdapter(DependencyProvider):
    """Resolves dependencies against system packages via find_package()."""

    name = "find_package"

    def resolve(self, dependency: DependencyModel, context: ResolutionContext) -> DependencyModel:
        """Fill the find_package name and imported targets.

        Args:
            dependency: The frozen dependency to complete.
            context: Lockfile contents and resolution flags (unused here;
                metadata comes from overrides and the registry, never the
                network).

        Returns:
            The dependency with cmake_name and link_targets filled.

        Raises:
            DependencyError: For a package the registry does not know and
                the user did not describe with overrides.
        """
        del context
        return fill_metadata(dependency)


def fill_metadata(dependency: DependencyModel) -> DependencyModel:
    """Fill a dependency's find_package name and imported targets.

    Shared by every adapter (they all emit find_package one way or another)
    and by the API layer, which needs the imported targets at freeze time to
    build link edges.

    Args:
        dependency: The dependency to complete, possibly carrying overrides.

    Returns:
        The dependency with cmake_name and link_targets filled.

    Raises:
        DependencyError: For a package the registry does not know and the
            user did not describe with overrides.
    """
    return replace(
        dependency,
        cmake_name=_cmake_name(dependency),
        link_targets=link_targets(dependency),
    )


def link_targets(dependency: DependencyModel) -> tuple[str, ...]:
    """Determine the imported targets consumers of a dependency link.

    Args:
        dependency: The dependency, possibly carrying user overrides.

    Returns:
        Explicit override targets when given, otherwise registry targets
        (with components expanded through the registry's template).

    Raises:
        DependencyError: When the targets cannot be known: an unknown
            package without a targets= override, or components requested
            for a package without per-component targets.
    """
    if dependency.link_targets:
        return dependency.link_targets
    entry = registry_entry(dependency.name)
    if entry is None:
        raise _unknown_package_error(dependency)
    if dependency.components:
        if entry.component_target_template is None:
            raise DependencyError(
                f"Package {dependency.name!r} does not take components, but "
                f"components={list(dependency.components)!r} was requested. Drop "
                f"the components argument, or pass targets=[...] naming the "
                f"imported targets explicitly."
            )
        template = entry.component_target_template
        return tuple(template.format(component=component) for component in dependency.components)
    return entry.targets


def _cmake_name(dependency: DependencyModel) -> str:
    """Determine the name the emitted find_package() call uses.

    Args:
        dependency: The dependency, possibly carrying user overrides.

    Returns:
        The override when given, the registry name when known, and the
        plain package name when explicit targets make guessing safe.

    Raises:
        DependencyError: For an unknown package with no overrides at all.
    """
    if dependency.cmake_name is not None:
        return dependency.cmake_name
    entry = registry_entry(dependency.name)
    if entry is not None:
        return entry.cmake_name
    if dependency.link_targets:
        return dependency.name
    raise _unknown_package_error(dependency)


def _unknown_package_error(dependency: DependencyModel) -> DependencyError:
    """Build the error for a package neither the registry nor the user knows.

    Args:
        dependency: The unresolvable dependency.

    Returns:
        The ready-to-raise error, listing known packages and the overrides
        that make any package usable.
    """
    known = ", ".join(known_packages())
    return DependencyError(
        f"Unknown package {dependency.name!r}: the built-in registry only knows "
        f"{known}. To use it anyway, tell depends() what CMake should see, for "
        f'example depends("{dependency.name}/{dependency.version}", '
        f'cmake_name="{dependency.name}", targets=["{dependency.name}::'
        f'{dependency.name}"], url=..., sha256=...).'
    )
