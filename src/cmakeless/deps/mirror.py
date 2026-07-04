# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Reading and writing cmakeless.mirror.json: local/offline package sources.

'cmakeless vendor' populates this file with file:// URIs pointing at
downloaded archives; a later --offline build consults it before falling back
to (or, offline, refusing) the upstream URL a package would otherwise fetch
from. Same determinism conventions as cmakeless.lock: plain JSON, sorted
keys, two-space indent, LF newlines.
"""

from __future__ import annotations

import json
from pathlib import Path

MIRROR_FILE_NAME = "cmakeless.mirror.json"
MIRROR_SCHEMA_VERSION = 1


def read_mirror_map(root: Path) -> dict[str, str]:
    """Load the mirror map, tolerating its absence.

    Args:
        root: The project root, usually where cmakeless.mirror.json lives.

    Returns:
        Package name to mirror URL, empty when the file does not exist.
    """
    path = root / MIRROR_FILE_NAME
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return dict(raw.get("mirrors", {}))


def write_mirror_map(root: Path, mirrors: dict[str, str]) -> None:
    """Write the mirror map, byte-deterministically.

    Args:
        root: The project root to write cmakeless.mirror.json into.
        mirrors: Package name to mirror URL.
    """
    document = {"schema": MIRROR_SCHEMA_VERSION, "mirrors": mirrors}
    text = json.dumps(document, indent=2, sort_keys=True) + "\n"
    (root / MIRROR_FILE_NAME).write_text(text, encoding="utf-8", newline="\n")
