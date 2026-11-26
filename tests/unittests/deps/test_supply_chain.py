"""Pin provenance, strict mode, scheme checks, streamed downloads, reproducible SBOMs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from cmakeless.deps.download import check_url, stream_sha256, stream_to_file
from cmakeless.deps.fetchcontent import AutoAdapter
from cmakeless.deps.lockfile import LockData, LockedPackage, read_lockfile, write_lockfile
from cmakeless.deps.provider import ResolutionContext
from cmakeless.deps.sbom import generate_cyclonedx, generate_spdx, reproducible_timestamp
from cmakeless.errors import DependencyError
from cmakeless.model.nodes import DependencyModel

PAYLOAD = b"archive-bytes"
DIGEST = hashlib.sha256(PAYLOAD).hexdigest()


def _context(
    *, strict: bool = False, locked: LockedPackage | None = None, **flags: object
) -> ResolutionContext:
    """A resolution context around at most one locked package."""
    packages = {locked.name: locked} if locked is not None else {}
    return ResolutionContext(
        root_dir=Path(), lock=LockData(packages=packages), strict=strict, **flags
    )  # type: ignore[arg-type]


def _custom(url: str = "https://example.test/pkg-1.0.tar.gz", **fields: object) -> DependencyModel:
    """A dependency outside the registry, so its pin must come from elsewhere."""
    return DependencyModel(
        name="pkg",
        version="1.0",
        cmake_name="pkg",
        link_targets=("pkg::pkg",),
        url=url,
        **fields,  # type: ignore[arg-type]
    )


def test_a_downloaded_pin_is_recorded_as_trust_on_first_use() -> None:
    """A hash nobody curated is marked tofu, so audits can find it."""
    resolved = AutoAdapter(download=lambda _url: PAYLOAD).resolve(_custom(), _context())
    assert (resolved.sha256, resolved.pin_source) == (DIGEST, "tofu")


def test_a_user_supplied_hash_is_recorded_as_user() -> None:
    """An explicit sha256= is the user's own pin."""
    adapter = AutoAdapter(download=lambda _url: pytest.fail("no download"))
    resolved = adapter.resolve(_custom(sha256=DIGEST), _context())
    assert resolved.pin_source == "user"


def test_strict_mode_refuses_trust_on_first_use() -> None:
    """Strict supply chains refuse hashes nobody reviewed."""
    with pytest.raises(DependencyError, match=r"trust on\s+first use"):
        AutoAdapter(download=lambda _url: PAYLOAD).resolve(_custom(), _context(strict=True))


def test_strict_mode_accepts_a_reviewed_lock_entry() -> None:
    """An approved pin passes strict mode without any download."""
    locked = LockedPackage(
        name="pkg",
        version="1.0",
        backend="auto",
        cmake_name="pkg",
        targets=("pkg::pkg",),
        url="https://example.test/pkg-1.0.tar.gz",
        sha256=DIGEST,
        pin_source="reviewed",
    )
    adapter = AutoAdapter(download=lambda _url: pytest.fail("no download"))
    resolved = adapter.resolve(_custom(), _context(strict=True, locked=locked))
    assert resolved.pin_source == "reviewed"


def test_strict_mode_refuses_plain_http() -> None:
    """HTTP pins can be swapped in transit, so strict mode refuses them."""
    with pytest.raises(DependencyError, match="plain HTTP"):
        check_url("http://example.test/a.tar.gz", name="pkg", strict=True)


def test_plain_http_only_warns_outside_strict_mode(capsys: pytest.CaptureFixture[str]) -> None:
    """Default mode keeps working but says so."""
    check_url("http://example.test/a.tar.gz", name="pkg", strict=False)
    assert "plain HTTP" in capsys.readouterr().err


@pytest.mark.parametrize("url", ["ftp://example.test/a.tar.gz", "gopher://x/y"])
def test_unfetchable_schemes_are_always_refused(url: str) -> None:
    """Only https, http, and file URLs can be fetched."""
    with pytest.raises(DependencyError, match="can be fetched"):
        check_url(url, name="pkg", strict=False)


def test_streamed_downloads_hash_without_holding_the_archive(tmp_path: Path) -> None:
    """A file:// URL streams through the same chunked hasher, and to disk."""
    source = tmp_path / "archive.tar.gz"
    source.write_bytes(PAYLOAD * 1000)
    url = source.as_uri()
    expected = hashlib.sha256(PAYLOAD * 1000).hexdigest()
    assert stream_sha256(url) == expected
    dest = tmp_path / "copy.tar.gz"
    assert stream_to_file(url, dest) == expected
    assert dest.read_bytes() == PAYLOAD * 1000
    assert not (tmp_path / "copy.tar.gz.partial").exists()


def test_the_lockfile_round_trips_pin_provenance(tmp_path: Path) -> None:
    """pin_source survives a write and a read; old lockfiles read as None."""
    path = tmp_path / "cmakeless.lock"
    package = LockedPackage(
        name="fmt", version="10.2.1", backend="auto", cmake_name="fmt", targets=("fmt::fmt",),
        url="https://x", sha256=DIGEST, pin_source="registry",
    )  # fmt: skip
    write_lockfile(path, {"fmt": package})
    assert read_lockfile(path).packages["fmt"].pin_source == "registry"
    raw = json.loads(path.read_text(encoding="utf-8"))
    del raw["packages"]["fmt"]["pin_source"]
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert read_lockfile(path).packages["fmt"].pin_source is None


def _lock() -> LockData:
    """A one-package lock."""
    package = LockedPackage(
        name="fmt", version="10.2.1", backend="auto", cmake_name="fmt", targets=("fmt::fmt",),
        url="https://x", sha256=DIGEST,
    )  # fmt: skip
    return LockData(packages={"fmt": package})


def test_sbom_identifiers_depend_only_on_the_inventory() -> None:
    """The same lock always produces the same document identifiers."""
    first = generate_cyclonedx(_lock(), project_name="demo", project_version="1.0", timestamp="T")
    second = generate_cyclonedx(_lock(), project_name="demo", project_version="1.0", timestamp="T")
    assert first == second
    spdx = generate_spdx(_lock(), project_name="demo", project_version="1.0", created="T")
    assert (
        spdx["documentNamespace"]
        == generate_spdx(_lock(), project_name="demo", project_version="1.0", created="T")[
            "documentNamespace"
        ]
    )


def test_source_date_epoch_pins_the_sbom_timestamp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SOURCE_DATE_EPOCH, the reproducible-builds convention, wins."""
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    assert reproducible_timestamp(tmp_path) == "2023-11-14T22:13:20Z"
