# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Downloading every locked dependency for zero-network, --offline builds.

'cmakeless vendor' downloads each fetchable package's pinned archive once,
verifies it against its locked SHA256, and records the local copy in
cmakeless.mirror.json as a file:// URI, so a later --offline build resolves
every package from disk with no extra configuration.
"""

from __future__ import annotations

import hashlib
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from cmakeless.deps.lockfile import LockData
from cmakeless.deps.mirror import write_mirror_map
from cmakeless.errors import DependencyError

_DOWNLOAD_TIMEOUT_SECONDS = 60.0

# Vendoring only ever makes sense for a URL that would otherwise need a real
# network fetch; rejecting anything else (file://, ftp://, ...) up front is
# both the correct behavior and the standard mitigation for urlopen's
# "audit url open for permitted schemes" warning (Bandit B310).
_ALLOWED_SCHEMES = frozenset({"http", "https"})


def vendor_packages(lock: LockData, *, directory: Path, root_dir: Path) -> int:
    """Download every fetchable locked package's archive into a vendor directory.

    Packages with no ``url`` (resolved purely through find_package(), or
    through vcpkg/Conan) are skipped: there is no archive to vendor for them.

    Args:
        lock: The project's resolved dependency inventory.
        directory: Where to write the downloaded archives.
        root_dir: The project root, so cmakeless.mirror.json lands next to
            cmakeless.lock.

    Returns:
        The number of archives downloaded.

    Raises:
        DependencyError: When a download fails, or a downloaded archive's
            hash does not match its locked pin.
    """
    directory.mkdir(parents=True, exist_ok=True)
    mirrors: dict[str, str] = {}
    for package in sorted(lock.packages.values(), key=lambda candidate: candidate.name):
        if package.url is None:
            continue
        dest = directory / f"{package.name}-{_archive_name(package.url, package.version)}"
        _download_and_verify(package.name, package.url, package.sha256, dest)
        mirrors[package.name] = _file_uri(dest.resolve())
    if mirrors:
        write_mirror_map(root_dir, mirrors)
    return len(mirrors)


def _file_uri(path: Path) -> str:
    """Build a file:// URI CMake's own FetchContent will accept for this path.

    CMake's URL-to-path handling for a file:// URL strips exactly the
    "file://" prefix rather than parsing the URI per RFC 8089, so
    Path.as_uri()'s three-slash Windows form (file:///C:/...) leaves a
    spurious leading slash before the drive letter once CMake strips the
    prefix. Two slashes (file://C:/...) is what CMake actually needs there;
    a POSIX absolute path already starts with "/", so the same "file://" +
    as_posix() construction produces the correct three-slash form there.

    Args:
        path: The absolute local path to address.

    Returns:
        The file:// URI.
    """
    return f"file://{path.as_posix()}"


def _archive_name(url: str, version: str) -> str:
    """Derive a local archive filename from its URL, prefixed by the package.

    Args:
        url: The archive URL.
        version: The locked version, used as a fallback name when the URL's
            path has no filename segment at all.

    Returns:
        The URL's own last path segment (preserving its extension, so
        FetchContent still recognizes .tar.gz/.zip), or "<version>.archive"
        when the URL has none.
    """
    return Path(urlsplit(url).path).name or f"{version}.archive"


def _download_and_verify(name: str, url: str, sha256: str | None, dest: Path) -> None:
    """Download one archive and verify it against its locked hash.

    Args:
        name: The package name, for error messages.
        url: The archive URL to download.
        sha256: The locked hash to verify against, or None to skip
            verification (a package pinned without one).
        dest: Where to write the downloaded archive.

    Raises:
        DependencyError: When ``url`` is not http(s), the download fails, or
            the downloaded bytes do not match ``sha256``.
    """
    if urlsplit(url).scheme not in _ALLOWED_SCHEMES:
        raise DependencyError(
            f"Refusing to vendor package {name!r} from {url!r}: only http(s) "
            f"URLs can be vendored. Fix the URL in cmakeless.lock (run "
            f"`cmakeless lock` to regenerate it)."
        )
    try:
        with urllib.request.urlopen(  # nosec B310 - scheme checked above
            url, timeout=_DOWNLOAD_TIMEOUT_SECONDS
        ) as response:
            payload = response.read()
    except (urllib.error.URLError, OSError) as error:
        raise DependencyError(
            f"Could not download {url} to vendor package {name!r} ({error}). "
            f"Check the URL and your network, then rerun `cmakeless vendor`."
        ) from error
    if sha256 is not None:
        digest = hashlib.sha256(payload).hexdigest()
        if digest != sha256:
            raise DependencyError(
                f"Downloaded archive for {name!r} does not match its locked "
                f"SHA256 ({digest} != {sha256}). The upstream archive may have "
                f"changed; run `cmakeless lock` to refresh the pin, then vendor "
                f"again."
            )
    dest.write_bytes(payload)
