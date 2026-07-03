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
from cmakeless.deps.resolver import provider_for, resolve_dependencies

__all__ = [
    "LOCKFILE_NAME",
    "DependencyProvider",
    "LockData",
    "LockedPackage",
    "ResolutionContext",
    "collect_tree_dependencies",
    "provider_for",
    "read_lockfile",
    "resolve_dependencies",
]
