"""The auto strategy's pin priority: lock, overrides, registry, download."""

from __future__ import annotations

import hashlib
import urllib.error
from pathlib import Path

import pytest

from cmakeless.deps.fetchcontent import AutoAdapter
from cmakeless.deps.lockfile import LockData, LockedPackage
from cmakeless.deps.provider import ResolutionContext
from cmakeless.errors import DependencyError
from cmakeless.model.nodes import DependencyModel

FMT_URL = "https://github.com/fmtlib/fmt/archive/refs/tags/10.2.1.tar.gz"


class RecordingDownloader:
    """A fake downloader that records requested URLs."""

    def __init__(self, payload: bytes = b"archive-bytes") -> None:
        """Script the payload every download returns."""
        self.payload = payload
        self.urls: list[str] = []

    def __call__(self, url: str) -> bytes:
        """Record the URL and return the scripted payload."""
        self.urls.append(url)
        return self.payload


def failing_download(url: str) -> bytes:
    """A downloader that must never be called."""
    raise AssertionError(f"unexpected network access: {url}")


def make_context(*, locked: LockedPackage | None = None, force: bool = False) -> ResolutionContext:
    """A resolution context around at most one locked package."""
    packages = {locked.name: locked} if locked is not None else {}
    return ResolutionContext(root_dir=Path(), lock=LockData(packages=packages), force=force)


def locked_fmt(*, version: str = "10.2.1") -> LockedPackage:
    """A locked fmt entry, with a version override for mismatch tests."""
    return LockedPackage(
        name="fmt",
        version=version,
        backend="auto",
        cmake_name="fmt",
        targets=("fmt::fmt",),
        url="https://example.invalid/locked.tar.gz",
        sha256="locked-hash",
    )


def test_curated_registry_pin_needs_no_network() -> None:
    """Curated registry pin needs no network."""
    adapter = AutoAdapter(download=failing_download)
    completed = adapter.resolve(DependencyModel(name="fmt", version="10.2.1"), make_context())
    assert completed.url == FMT_URL
    assert completed.sha256 is not None
    assert len(completed.sha256) == 64


def test_lock_entry_short_circuits_everything() -> None:
    """Lock entry short circuits everything."""
    adapter = AutoAdapter(download=failing_download)
    context = make_context(locked=locked_fmt())
    completed = adapter.resolve(DependencyModel(name="fmt", version="10.2.1"), context)
    assert completed.url == "https://example.invalid/locked.tar.gz"
    assert completed.sha256 == "locked-hash"


def test_version_mismatch_ignores_the_lock() -> None:
    """Version mismatch ignores the lock."""
    downloader = RecordingDownloader()
    adapter = AutoAdapter(download=downloader)
    context = make_context(locked=locked_fmt(version="9.0.0"))
    completed = adapter.resolve(DependencyModel(name="fmt", version="10.2.1"), context)
    # The curated registry pin for 10.2.1 wins; the stale lock is ignored.
    assert completed.url == FMT_URL
    assert completed.sha256 != "locked-hash"


def test_force_refresh_ignores_the_lock() -> None:
    """Force refresh ignores the lock."""
    adapter = AutoAdapter(download=failing_download)
    context = make_context(locked=locked_fmt(), force=True)
    completed = adapter.resolve(DependencyModel(name="fmt", version="10.2.1"), context)
    assert completed.url == FMT_URL


def test_uncurated_version_is_downloaded_and_hashed_once() -> None:
    """Uncurated version is downloaded and hashed once."""
    downloader = RecordingDownloader(payload=b"fmt-11")
    adapter = AutoAdapter(download=downloader)
    completed = adapter.resolve(DependencyModel(name="fmt", version="11.0.0"), make_context())
    assert downloader.urls == [FMT_URL.replace("10.2.1", "11.0.0")]
    assert completed.sha256 == hashlib.sha256(b"fmt-11").hexdigest()


def test_explicit_url_and_sha_need_no_network() -> None:
    """Explicit url and sha need no network."""
    adapter = AutoAdapter(download=failing_download)
    dependency = DependencyModel(
        name="obscurelib",
        version="1.0",
        link_targets=("obscure::lib",),
        url="https://example.com/obscure-1.0.tar.gz",
        sha256="feed" * 16,
    )
    completed = adapter.resolve(dependency, make_context())
    assert completed.url == "https://example.com/obscure-1.0.tar.gz"
    assert completed.sha256 == "feed" * 16


def test_explicit_url_without_sha_is_hashed() -> None:
    """Explicit url without sha is hashed."""
    downloader = RecordingDownloader(payload=b"obscure")
    adapter = AutoAdapter(download=downloader)
    dependency = DependencyModel(
        name="obscurelib",
        version="1.0",
        link_targets=("obscure::lib",),
        url="https://example.com/obscure-1.0.tar.gz",
    )
    completed = adapter.resolve(dependency, make_context())
    assert downloader.urls == ["https://example.com/obscure-1.0.tar.gz"]
    assert completed.sha256 == hashlib.sha256(b"obscure").hexdigest()


def test_not_fetchable_package_recommends_a_package_manager() -> None:
    """Not fetchable package recommends a package manager."""
    adapter = AutoAdapter(download=failing_download)
    dependency = DependencyModel(name="boost", version="1.84.0", components=("asio",))
    with pytest.raises(DependencyError, match="vcpkg"):
        adapter.resolve(dependency, make_context())


def test_download_failure_says_what_to_try_next() -> None:
    """Download failure says what to try next."""

    def broken_download(url: str) -> bytes:
        """Simulate an unreachable network."""
        raise urllib.error.URLError("no route to host")

    adapter = AutoAdapter(download=broken_download)
    with pytest.raises(DependencyError) as excinfo:
        adapter.resolve(DependencyModel(name="fmt", version="11.0.0"), make_context())
    message = str(excinfo.value)
    assert "fmt" in message
    assert "network" in message
    assert "sha256=" in message
