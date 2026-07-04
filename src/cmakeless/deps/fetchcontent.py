# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""The FetchContent adapter and the default find_package-then-fetch strategy.

cmakeless never builds sources itself; it pins a URL and SHA256 into the
emitted FetchContent_Declare() and lets CMake do the real work. The pin
comes, in priority order, from the lockfile, the user's explicit overrides,
the registry's curated hashes, or a one-time download-and-hash whose result
is then locked for everyone else.
"""

from __future__ import annotations

import hashlib
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import replace

from cmakeless.deps.find_package import FindPackageAdapter
from cmakeless.deps.provider import DependencyProvider, ResolutionContext
from cmakeless.deps.registry import registry_entry
from cmakeless.errors import DependencyError
from cmakeless.model.nodes import DependencyModel

_DOWNLOAD_TIMEOUT_SECONDS = 60.0


class AutoAdapter(DependencyProvider):
    """The default strategy: system package first, pinned source fetch second.

    The emitted CMake tries find_package() and falls back to FetchContent
    with a pinned URL and hash, so this adapter must complete both halves:
    the find_package metadata and the fetch pin.
    """

    name = "auto"

    def __init__(self, *, download: Callable[[str], bytes] | None = None) -> None:
        """Create the adapter, optionally with a custom downloader.

        Args:
            download: Replacement for the urllib downloader, used by tests
                to keep resolution offline; None uses the real network.
        """
        self._find_package = FindPackageAdapter()
        self._download = download if download is not None else _download_archive

    def resolve(self, dependency: DependencyModel, context: ResolutionContext) -> DependencyModel:
        """Fill metadata and the fetch pin for one dependency.

        Args:
            dependency: The frozen dependency to complete.
            context: Lockfile contents and resolution flags.

        Returns:
            The dependency with cmake_name, link_targets, url, and sha256
            filled.

        Raises:
            DependencyError: When the package is unknown, not fetchable, or
                its archive cannot be downloaded for hashing.
        """
        completed = self._find_package.resolve(dependency, context)
        locked = _locked_pin(completed, context)
        if locked is not None:
            return replace(completed, url=locked[0], sha256=locked[1])
        url, sha256 = self._pin(completed)
        return replace(completed, url=url, sha256=sha256)

    def _pin(self, dependency: DependencyModel) -> tuple[str, str]:
        """Produce the fetch pin from overrides, the registry, or a download.

        Args:
            dependency: The dependency, its metadata already filled.

        Returns:
            The (url, sha256) pair to emit and lock.

        Raises:
            DependencyError: When the package is not fetchable or the
                archive cannot be downloaded.
        """
        url = dependency.url if dependency.url is not None else _registry_url(dependency)
        if dependency.sha256 is not None:
            return (url, dependency.sha256)
        if dependency.url is None:
            entry = registry_entry(dependency.name)
            if entry is not None and dependency.version in entry.sha256_by_version:
                return (url, entry.sha256_by_version[dependency.version])
        return (url, self._download_and_hash(dependency, url))

    def _download_and_hash(self, dependency: DependencyModel, url: str) -> str:
        """Download an archive once and hash it, trust-on-first-use.

        The result is recorded in cmakeless.lock, so no other machine (and
        no later run) repeats the download or the trust decision.

        Args:
            dependency: The dependency being pinned, for error messages.
            url: The archive URL to download.

        Returns:
            The archive's SHA256 hex digest.

        Raises:
            DependencyError: When the download fails.
        """
        try:
            payload = self._download(url)
        except (urllib.error.URLError, OSError) as error:
            raise DependencyError(
                f"Could not download {url} to pin package {dependency.name!r} "
                f"({error}). Check the URL and your network, or pass url= and "
                f"sha256= to depends() explicitly."
            ) from error
        return hashlib.sha256(payload).hexdigest()


def _locked_pin(dependency: DependencyModel, context: ResolutionContext) -> tuple[str, str] | None:
    """Look for a reusable pin in the lockfile.

    Args:
        dependency: The dependency being resolved.
        context: Lockfile contents and resolution flags.

    Returns:
        The locked (url, sha256) when the lock has a matching, complete
        entry and the user did not force a refresh; None otherwise.
    """
    if context.force:
        return None
    locked = context.lock.packages.get(dependency.name)
    if locked is None or locked.version != dependency.version or locked.backend != "auto":
        return None
    if locked.url is None or locked.sha256 is None:
        return None
    return (locked.url, locked.sha256)


def _registry_url(dependency: DependencyModel) -> str:
    """Build the archive URL from the registry's template.

    Args:
        dependency: The dependency being pinned.

    Returns:
        The formatted URL.

    Raises:
        DependencyError: When the registry marks the package as not
            fetchable from source (boost, zlib), or does not know it.
    """
    entry = registry_entry(dependency.name)
    if entry is None or entry.url_template is None:
        raise DependencyError(
            f"Package {dependency.name!r} cannot be fetched from source. Opt into "
            f'a package manager with project.package_manager = "vcpkg" (or '
            f'"conan"), or pass url= and sha256= to depends() to fetch a custom '
            f"archive."
        )
    return entry.url_template.format(version=dependency.version)


def _download_archive(url: str) -> bytes:
    """Download one archive over HTTPS.

    Args:
        url: The archive URL.

    Returns:
        The raw archive bytes.
    """
    with urllib.request.urlopen(url, timeout=_DOWNLOAD_TIMEOUT_SECONDS) as response:
        return bytes(response.read())
