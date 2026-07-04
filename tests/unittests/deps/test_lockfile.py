# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Lockfile round-trips, byte determinism, and schema guarding."""

from __future__ import annotations

from pathlib import Path

import pytest

from cmakeless.deps.lockfile import (
    LOCK_SCHEMA_VERSION,
    LockedPackage,
    read_lockfile,
    write_lockfile,
)
from cmakeless.errors import DependencyError


def fmt_package() -> LockedPackage:
    """A representative locked package with a fetch pin."""
    return LockedPackage(
        name="fmt",
        version="10.2.1",
        backend="auto",
        cmake_name="fmt",
        targets=("fmt::fmt",),
        url="https://github.com/fmtlib/fmt/archive/refs/tags/10.2.1.tar.gz",
        sha256="deadbeef" * 8,
    )


def boost_package() -> LockedPackage:
    """A representative locked package without a fetch pin."""
    return LockedPackage(
        name="boost",
        version="1.84.0",
        backend="vcpkg",
        cmake_name="Boost",
        targets=("Boost::asio",),
    )


def test_round_trip_preserves_everything(tmp_path: Path) -> None:
    """Round trip preserves everything."""
    path = tmp_path / "cmakeless.lock"
    write_lockfile(
        path,
        {"fmt": fmt_package(), "boost": boost_package()},
        vcpkg_baseline="abc123",
    )
    lock = read_lockfile(path)
    assert lock.packages["fmt"] == fmt_package()
    assert lock.packages["boost"] == boost_package()
    assert lock.vcpkg_baseline == "abc123"


def test_output_is_byte_deterministic(tmp_path: Path) -> None:
    """Output is byte deterministic."""
    first = tmp_path / "first.lock"
    second = tmp_path / "second.lock"
    write_lockfile(first, {"fmt": fmt_package(), "boost": boost_package()})
    write_lockfile(second, {"boost": boost_package(), "fmt": fmt_package()})
    assert first.read_bytes() == second.read_bytes()


def test_missing_file_reads_as_empty(tmp_path: Path) -> None:
    """Missing file reads as empty."""
    lock = read_lockfile(tmp_path / "cmakeless.lock")
    assert lock.packages == {}
    assert lock.vcpkg_baseline is None


def test_invalid_json_says_what_to_try_next(tmp_path: Path) -> None:
    """Invalid json says what to try next."""
    path = tmp_path / "cmakeless.lock"
    path.write_text("not json {", encoding="utf-8")
    with pytest.raises(DependencyError, match="Delete it and rerun"):
        read_lockfile(path)


def test_unknown_schema_is_rejected(tmp_path: Path) -> None:
    """Unknown schema is rejected."""
    path = tmp_path / "cmakeless.lock"
    path.write_text(f'{{"schema": {LOCK_SCHEMA_VERSION + 1}, "packages": {{}}}}', encoding="utf-8")
    with pytest.raises(DependencyError, match="schema"):
        read_lockfile(path)


def test_lockfile_ends_with_a_newline(tmp_path: Path) -> None:
    """Lockfile ends with a newline."""
    path = tmp_path / "cmakeless.lock"
    write_lockfile(path, {"fmt": fmt_package()})
    assert path.read_bytes().endswith(b"\n")
