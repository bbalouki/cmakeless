"""Dependency-provider strategies: one Adapter per acquisition backend.

target.depends("fmt/10.2.1") never changes when the backend does; these
adapters translate that single spec into find_package calls, pinned
FetchContent blocks, vcpkg manifests, or Conan manifests.

This package re-exports every public class and function from its submodules,
so `from cmakeless.deps import ...` reaches the whole provider surface.
"""

from cmakeless.deps.conan import CONAN_MANIFEST_NAME, ConanAdapter
from cmakeless.deps.fetchcontent import AutoAdapter
from cmakeless.deps.find_package import FindPackageAdapter, fill_metadata, link_targets
from cmakeless.deps.lockfile import (
    LOCK_SCHEMA_VERSION,
    LOCKFILE_NAME,
    LockData,
    LockedPackage,
    read_lockfile,
    write_lockfile,
)
from cmakeless.deps.mirror import (
    MIRROR_FILE_NAME,
    MIRROR_SCHEMA_VERSION,
    read_mirror_map,
    write_mirror_map,
)
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
from cmakeless.deps.vcpkg import VCPKG_MANIFEST_NAME, VcpkgAdapter, vcpkg_root
from cmakeless.deps.vendor import vendor_packages

__all__ = [
    "CONAN_MANIFEST_NAME",
    "LOCKFILE_NAME",
    "LOCK_SCHEMA_VERSION",
    "MIRROR_FILE_NAME",
    "MIRROR_SCHEMA_VERSION",
    "PLUGIN_ENTRY_POINT_GROUP",
    "SBOM_FORMATS",
    "VCPKG_MANIFEST_NAME",
    "AutoAdapter",
    "ConanAdapter",
    "DependencyProvider",
    "FindPackageAdapter",
    "LockData",
    "LockedPackage",
    "RegistryEntry",
    "ResolutionContext",
    "VcpkgAdapter",
    "collect_tree_dependencies",
    "fill_metadata",
    "generate_cyclonedx",
    "generate_spdx",
    "known_packages",
    "link_targets",
    "provider_for",
    "read_lockfile",
    "read_mirror_map",
    "register_dependency",
    "registry_entry",
    "resolve_dependencies",
    "vcpkg_root",
    "vendor_packages",
    "write_lockfile",
    "write_mirror_map",
]
