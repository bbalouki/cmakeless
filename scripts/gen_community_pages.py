# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Mirror the repository's community health files into the doc site's nav.

CONTRIBUTING.md, CODE_OF_CONDUCT.md, SECURITY.md, and CHANGELOG.md live at
the repository root, where GitHub expects them so it can surface them in
its own UI. Copying them into `docs/` by hand would leave two files to keep
in sync, so this script mirrors them into the generated site at build time
instead: the root file stays the single source of truth, and relative links
between them are rewritten to point at their generated counterparts.
"""

from __future__ import annotations

import re
from pathlib import Path

import mkdocs_gen_files

_ROOT = Path(__file__).resolve().parent.parent

# Source filename (repository root) -> generated doc filename (site nav).
_PAGES = {
    "CONTRIBUTING.md": "contributing.md",
    "CODE_OF_CONDUCT.md": "code_of_conduct.md",
    "SECURITY.md": "security.md",
    "CHANGELOG.md": "changelog.md",
}

# Matches markdown links to any of these files, with or without the `docs/`
# prefix they carry when pointing from the repository root into docs/.
_LINK_TARGET = re.compile(r"\]\((?:docs/)?([A-Za-z0-9_.-]+\.md)(#[^)]*)?\)")


def _rewrite_link(match: re.Match[str]) -> str:
    """Point a relative link at its generated doc page, unchanged otherwise."""
    target, anchor = match.group(1), match.group(2) or ""
    target = _PAGES.get(target, target)
    return f"]({target}{anchor})"


for source_name, doc_name in _PAGES.items():
    source_path = _ROOT / source_name
    content = _LINK_TARGET.sub(_rewrite_link, source_path.read_text(encoding="utf-8"))

    with mkdocs_gen_files.open(doc_name, "w") as doc_file:
        doc_file.write(content)

    mkdocs_gen_files.set_edit_path(doc_name, source_name)
