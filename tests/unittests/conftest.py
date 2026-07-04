# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Shared fixtures for the unit tests."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """A minimal on-disk C++ project layout with one real source file."""
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "main.cpp").write_text("auto main() -> int { return 0; }\n", encoding="utf-8")
    return tmp_path
