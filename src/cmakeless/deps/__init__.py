# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Dependency-provider strategies: one Adapter per acquisition backend.

target.depends("fmt/10.2.1") never changes when the backend does; these
adapters translate that single spec into find_package calls, pinned
FetchContent blocks, vcpkg manifests, or Conan manifests.
"""

from cmakeless.deps.lockfile import LOCKFILE_NAME, LockData, LockedPackage, read_lockfile
from cmakeless.deps.provider import (
    DependencyProvider,
    ResolutionContext,
    collect_tree_dependencies,
)
from cmakeless.deps.registry import (
    PLUGIN_ENTRY_POINT_GROUP,
    RegistryEntry,
    known_packages,
    registry_entry,
)
from cmakeless.deps.registry import register as register_dependency
from cmakeless.deps.resolver import provider_for, resolve_dependencies

__all__ = [
    "LOCKFILE_NAME",
    "PLUGIN_ENTRY_POINT_GROUP",
    "DependencyProvider",
    "LockData",
    "LockedPackage",
    "RegistryEntry",
    "ResolutionContext",
    "collect_tree_dependencies",
    "known_packages",
    "provider_for",
    "read_lockfile",
    "register_dependency",
    "registry_entry",
    "resolve_dependencies",
]
