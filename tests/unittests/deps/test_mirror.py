# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Reading and writing cmakeless.mirror.json."""

from __future__ import annotations

from pathlib import Path

from cmakeless.deps.mirror import MIRROR_FILE_NAME, read_mirror_map, write_mirror_map


def test_missing_mirror_map_is_empty(tmp_path: Path) -> None:
    """Missing mirror map is empty."""
    assert read_mirror_map(tmp_path) == {}


def test_write_then_read_round_trips(tmp_path: Path) -> None:
    """Write then read round trips."""
    mirrors = {"fmt": "file:///vendor/fmt.tar.gz", "spdlog": "file:///vendor/spdlog.tar.gz"}
    write_mirror_map(tmp_path, mirrors)
    assert read_mirror_map(tmp_path) == mirrors


def test_written_file_is_deterministic(tmp_path: Path) -> None:
    """Written file is deterministic."""
    write_mirror_map(tmp_path, {"b": "file:///b", "a": "file:///a"})
    text = (tmp_path / MIRROR_FILE_NAME).read_text(encoding="utf-8")
    assert text.index('"a"') < text.index('"b"')
    assert text.endswith("\n")
