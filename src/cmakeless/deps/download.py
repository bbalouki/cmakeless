"""Streamed, retried, scheme-checked archive downloads.

Archives are hashed in fixed-size chunks rather than read whole, so a
multi-hundred-megabyte Boost or OpenCV tarball never sits in memory. urllib
already honors HTTPS_PROXY, NO_PROXY, and SSL_CERT_FILE, which is how
corporate proxies and custom certificate authorities are configured.
"""

from __future__ import annotations

import hashlib
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import BinaryIO
from urllib.parse import urlsplit

from cmakeless.errors import DependencyError

DOWNLOAD_TIMEOUT_SECONDS = 60.0

# Schemes a dependency URL may use. file:// serves vendored mirrors; plain
# http is accepted only outside strict supply-chain mode, with a warning.
FETCHABLE_SCHEMES: frozenset[str] = frozenset({"https", "http", "file"})
INSECURE_SCHEMES: frozenset[str] = frozenset({"http"})

_CHUNK_BYTES = 1 << 20
_ATTEMPTS = 3
_BACKOFF_SECONDS = 1.0
_SERVER_ERROR_FLOOR = 500


def check_url(url: str, *, name: str, strict: bool) -> None:
    """Refuse a dependency URL whose scheme cannot be fetched safely.

    Args:
        url: The archive URL.
        name: The package name, for messages.
        strict: True in supply_chain="strict" mode, where plain HTTP is an
            error rather than a warning.

    Raises:
        DependencyError: When the scheme is not fetchable, or is insecure
            in strict mode.
    """
    scheme = urlsplit(url).scheme
    if scheme not in FETCHABLE_SCHEMES:
        raise DependencyError(
            f"Package {name!r} uses {url!r}, but only https://, http://, and "
            f"file:// URLs can be fetched. Point it at an https:// archive."
        )
    if scheme in INSECURE_SCHEMES:
        if strict:
            raise DependencyError(
                f"Package {name!r} uses plain HTTP ({url}), which supply_chain="
                f'"strict" refuses: anyone on the network path could swap the '
                f"archive. Use the https:// URL, or vendor the archive."
            )
        print(
            f"[cmakeless] Warning: package {name!r} is fetched over plain HTTP ({url}); "
            f"prefer https://.",
            file=sys.stderr,
        )


def stream_sha256(url: str) -> str:
    """Download an archive and hash it without keeping it.

    Args:
        url: The archive URL.

    Returns:
        The SHA256 hex digest.

    Raises:
        urllib.error.URLError: When every attempt fails.
        OSError: When the connection fails on every attempt.
    """
    return _with_retries(url, None)


def stream_to_file(url: str, dest: Path) -> str:
    """Download an archive to a file, hashing it as it streams.

    Args:
        url: The archive URL.
        dest: Where to write it; replaced only after a complete download.

    Returns:
        The SHA256 hex digest.

    Raises:
        urllib.error.URLError: When every attempt fails.
        OSError: When the connection fails on every attempt.
    """
    partial = dest.with_name(dest.name + ".partial")
    digest = _with_retries(url, partial)
    partial.replace(dest)
    return digest


def _with_retries(url: str, dest: Path | None) -> str:
    """Run one streamed download, retrying transient failures with backoff.

    Args:
        url: The archive URL.
        dest: Where to write the bytes, or None to only hash them.

    Returns:
        The SHA256 hex digest.

    Raises:
        urllib.error.URLError: The last failure, once attempts run out or
            the error is not transient.
    """
    for attempt in range(_ATTEMPTS):
        try:
            return _stream_once(url, dest)
        except urllib.error.HTTPError as error:
            if error.code < _SERVER_ERROR_FLOOR or attempt == _ATTEMPTS - 1:
                raise
        except (urllib.error.URLError, OSError):
            if attempt == _ATTEMPTS - 1:
                raise
        time.sleep(_BACKOFF_SECONDS * (2**attempt))
    raise AssertionError("the loop always returns or raises")


def _stream_once(url: str, dest: Path | None) -> str:
    """Download one archive in chunks, hashing as it goes.

    Args:
        url: The archive URL; its scheme was checked by the caller.
        dest: Where to write the bytes, or None to only hash them.

    Returns:
        The SHA256 hex digest.
    """
    hasher = hashlib.sha256()
    with urllib.request.urlopen(  # nosec B310 - callers run check_url() first
        url, timeout=DOWNLOAD_TIMEOUT_SECONDS
    ) as response:
        sink: BinaryIO | None = dest.open("wb") if dest is not None else None
        try:
            while chunk := response.read(_CHUNK_BYTES):
                hasher.update(chunk)
                if sink is not None:
                    sink.write(chunk)
        finally:
            if sink is not None:
                sink.close()
    return hasher.hexdigest()
