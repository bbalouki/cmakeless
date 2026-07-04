# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Dependency-provider strategies: one Adapter per acquisition backend.

target.depends("fmt/10.2.1") never changes when the backend does; these
adapters translate that single spec into find_package calls, pinned
FetchContent blocks, vcpkg manifests, or Conan manifests.
"""

from cmakeless.deps.lockfile import LOCKFILE_NAME, LockData, LockedPackage, read_lockfile
from cmakeless.deps.mirror import MIRROR_FILE_NAME, read_mirror_map, write_mirror_map
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
from cmakeless.deps.sbom import SBOM_FORMATS, generate_cyclonedx, generate_spdx
from cmakeless.deps.vendor import vendor_packages

__all__ = [
    "LOCKFILE_NAME",
    "MIRROR_FILE_NAME",
    "PLUGIN_ENTRY_POINT_GROUP",
    "SBOM_FORMATS",
    "DependencyProvider",
    "LockData",
    "LockedPackage",
    "RegistryEntry",
    "ResolutionContext",
    "collect_tree_dependencies",
    "generate_cyclonedx",
    "generate_spdx",
    "known_packages",
    "provider_for",
    "read_lockfile",
    "read_mirror_map",
    "register_dependency",
    "registry_entry",
    "resolve_dependencies",
    "vendor_packages",
    "write_mirror_map",
]
