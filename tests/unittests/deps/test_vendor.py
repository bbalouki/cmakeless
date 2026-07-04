# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Downloading locked dependencies for --offline builds ('cmakeless vendor')."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from cmakeless.deps.lockfile import LockData, LockedPackage
from cmakeless.deps.mirror import read_mirror_map
from cmakeless.deps.vendor import _file_uri, vendor_packages
from cmakeless.errors import DependencyError

_FMT_URL = "https://github.com/fmtlib/fmt/archive/refs/tags/10.2.1.tar.gz"


def make_lock(*, sha256: str | None) -> LockData:
    """A lockfile with one fetchable package and one find_package-only one."""
    return LockData(
        packages={
            "fmt": LockedPackage(
                name="fmt",
                version="10.2.1",
                backend="auto",
                cmake_name="fmt",
                targets=("fmt::fmt",),
                url=_FMT_URL,
                sha256=sha256,
            ),
            "googletest": LockedPackage(
                name="googletest",
                version="1.14.0",
                backend="find_package",
                cmake_name="GTest",
                targets=("GTest::gtest",),
            ),
        }
    )


def test_skips_packages_without_a_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Skips packages without a url."""

    def refuse(url: str, timeout: float) -> object:
        """Fail the test if a download is attempted."""
        raise AssertionError(f"unexpected download: {url}")

    monkeypatch.setattr("cmakeless.deps.vendor.urllib.request.urlopen", refuse)
    lock = LockData(
        packages={
            "googletest": LockedPackage(
                name="googletest",
                version="1.14.0",
                backend="find_package",
                cmake_name="GTest",
                targets=("GTest::gtest",),
            )
        }
    )
    count = vendor_packages(lock, directory=tmp_path / "vendor", root_dir=tmp_path)
    assert count == 0
    assert not (tmp_path / "cmakeless.mirror.json").exists()


class _FakeResponse:
    """A urlopen()-style context manager returning scripted bytes."""

    def __init__(self, payload: bytes) -> None:
        """Script the payload this response returns."""
        self._payload = payload

    def __enter__(self) -> _FakeResponse:
        """Enter the context, returning self."""
        return self

    def __exit__(self, *exc_info: object) -> None:
        """Exit the context; nothing to clean up."""

    def read(self) -> bytes:
        """Return the scripted payload."""
        return self._payload


def test_downloads_verifies_and_writes_mirror_map(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Downloads, verifies, and writes the mirror map."""
    payload = b"fmt-archive-bytes"
    digest = hashlib.sha256(payload).hexdigest()
    monkeypatch.setattr(
        "cmakeless.deps.vendor.urllib.request.urlopen", lambda url, timeout: _FakeResponse(payload)
    )
    lock = make_lock(sha256=digest)
    vendor_dir = tmp_path / "vendor"
    count = vendor_packages(lock, directory=vendor_dir, root_dir=tmp_path)
    assert count == 1
    downloaded = list(vendor_dir.glob("*.tar.gz"))
    assert len(downloaded) == 1
    assert downloaded[0].read_bytes() == payload
    mirrors = read_mirror_map(tmp_path)
    assert mirrors["fmt"] == _file_uri(downloaded[0].resolve())
    assert "googletest" not in mirrors


def test_file_uri_strips_to_a_valid_path_after_the_file_scheme_prefix(tmp_path: Path) -> None:
    """A file:// URI, once 'file://' is stripped, is a valid absolute path.

    This is what CMake's own file:// handling actually does (a plain
    prefix strip, not full URI parsing), so the round trip must hold on
    every platform, Windows drive letters included.
    """
    path = tmp_path / "archive.tar.gz"
    uri = _file_uri(path)
    assert uri.startswith("file://")
    assert Path(uri.removeprefix("file://")) == path


def test_hash_mismatch_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Hash mismatch raises."""
    monkeypatch.setattr(
        "cmakeless.deps.vendor.urllib.request.urlopen",
        lambda url, timeout: _FakeResponse(b"unexpected-bytes"),
    )
    lock = make_lock(sha256="ab" * 32)
    with pytest.raises(DependencyError, match="does not match"):
        vendor_packages(lock, directory=tmp_path / "vendor", root_dir=tmp_path)
