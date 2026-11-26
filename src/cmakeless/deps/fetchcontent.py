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
from collections.abc import Callable
from dataclasses import replace

from cmakeless.deps.download import check_url, stream_sha256
from cmakeless.deps.find_package import FindPackageAdapter
from cmakeless.deps.provider import DependencyProvider, ResolutionContext
from cmakeless.deps.registry import registry_entry
from cmakeless.errors import DependencyError
from cmakeless.model.nodes import DependencyModel

# A pin is (url, sha256, how it was obtained).
type Pin = tuple[str, str, str]


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
        self._download = download

    def resolve(self, dependency: DependencyModel, context: ResolutionContext) -> DependencyModel:
        """Fill metadata and the fetch pin for one dependency.

        Args:
            dependency: The frozen dependency to complete.
            context: Lockfile contents and resolution flags.

        Returns:
            The dependency with cmake_name, link_targets, url, sha256, and
            pin_source filled.

        Raises:
            DependencyError: When the package is unknown, not fetchable, its
                archive cannot be downloaded for hashing, or strict mode
                refuses its pin.
        """
        completed = self._find_package.resolve(dependency, context)
        pin = _locked_pin(completed, context) or self._pin(completed, context)
        url, sha256, source = pin
        check_url(url, name=completed.name, strict=context.strict)
        if context.strict and source == "tofu":
            raise DependencyError(
                f"Package {completed.name!r} {completed.version} is pinned by trust on "
                f"first use (its hash is whatever the first download produced), which "
                f'supply_chain="strict" refuses. Pass sha256= to depends() from the '
                f"upstream release notes, or review the pin and approve it with "
                f"`cmakeless audit --approve {completed.name}`."
            )
        return replace(completed, url=url, sha256=sha256, pin_source=source)

    def _pin(self, dependency: DependencyModel, context: ResolutionContext) -> Pin:
        """Produce the fetch pin from overrides, the registry, or a download.

        The mirror map is deliberately not consulted here: it only ever
        substitutes the URL of an *already-resolved* package for emission
        (see resolve_dependencies()'s post-resolution mirror pass), so
        cmakeless.lock keeps recording the canonical upstream pin, not a
        machine-local vendor path.

        Args:
            dependency: The dependency, its metadata already filled.
            context: Lockfile contents and resolution flags, including the
                --offline setting.

        Returns:
            The (url, sha256, pin source) to emit and lock.

        Raises:
            DependencyError: When the package is not fetchable, offline
                resolution has no cached hash to use, or the archive cannot
                be downloaded.
        """
        url = dependency.url if dependency.url is not None else _registry_url(dependency)
        if dependency.sha256 is not None:
            return (url, dependency.sha256, "user")
        if dependency.url is None:
            entry = registry_entry(dependency.name)
            if entry is not None and dependency.version in entry.sha256_by_version:
                return (url, entry.sha256_by_version[dependency.version], "registry")
        if context.offline:
            raise DependencyError(
                f"Cannot resolve package {dependency.name!r} offline (--offline): "
                f"no cached hash and network access is disabled. Run "
                f"`cmakeless lock` once with network access first, or drop "
                f"--offline."
            )
        check_url(url, name=dependency.name, strict=context.strict)
        return (url, self._download_and_hash(dependency, url), "tofu")

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
            if self._download is not None:
                return hashlib.sha256(self._download(url)).hexdigest()
            return stream_sha256(url)
        except (urllib.error.URLError, OSError) as error:
            raise DependencyError(
                f"Could not download {url} to pin package {dependency.name!r} "
                f"({error}). Check the URL and your network (HTTPS_PROXY and "
                f"SSL_CERT_FILE configure a proxy or a custom certificate "
                f"authority), or pass url= and sha256= to depends() explicitly."
            ) from error


def _locked_pin(dependency: DependencyModel, context: ResolutionContext) -> Pin | None:
    """Look for a reusable pin in the lockfile.

    Args:
        dependency: The dependency being resolved.
        context: Lockfile contents and resolution flags.

    Returns:
        The locked (url, sha256, pin source) when the lock has a matching,
        complete entry and the user did not force a refresh of this
        package; None otherwise. A lockfile written before provenance was
        recorded counts as "tofu", since nothing says otherwise.
    """
    if context.force and (context.only is None or dependency.name in context.only):
        return None
    locked = context.lock.packages.get(dependency.name)
    if locked is None or locked.version != dependency.version or locked.backend != "auto":
        return None
    if locked.url is None or locked.sha256 is None:
        return None
    return (locked.url, locked.sha256, locked.pin_source or "tofu")


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
