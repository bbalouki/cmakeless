# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Prints a summary of the assets manifest: the always-run step project.add_custom_target() runs.

Run by CMake through add_custom_target(), not directly; the manifest path is
supplied by cmakelessfile.py's project.add_custom_target() call. A real
project would resize or pack images here; this stands in for that so the
example stays runnable without extra dependencies.
"""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    """Print each asset name listed in the manifest."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", help="Path to the assets manifest, one name per line")
    args = parser.parse_args()

    names = [
        line.strip()
        for line in Path(args.manifest).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    print(f"cooking {len(names)} asset(s): {', '.join(names)}")


if __name__ == "__main__":
    main()
