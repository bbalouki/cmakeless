# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Generate the API reference pages and their nav from the source tree.

As ARCHITECTURE.md's "Public API" section states, users only ever import
`cmakeless` itself and the classes it re-exports (defined under
`cmakeless.api`), plus the error hierarchy and observer event types read
back from a build. `cmakeless.model`, `cmakeless.emitter`, `cmakeless.driver`,
and `cmakeless.deps` are implementation detail the package layout
deliberately keeps unimportable in practice, so this script documents only
the modules that make up that public surface. Each one gets a page rendering
its docstrings via mkdocstrings, so the reference stays in sync with the
code without anyone hand-maintaining a page per module.
"""

from __future__ import annotations

from pathlib import Path

import mkdocs_gen_files

_nav = mkdocs_gen_files.Nav()

_ROOT = Path(__file__).resolve().parent.parent
_PACKAGE = _ROOT / "src" / "cmakeless"

_PUBLIC_MODULES = (
    _PACKAGE / "__init__.py",
    _PACKAGE / "errors.py",
    _PACKAGE / "observer.py",
    *sorted(_PACKAGE.glob("api/*.py")),
)


def _document(path: Path) -> None:
    """Render one module's docstrings to its generated reference page."""
    module_path = path.relative_to(_PACKAGE.parent).with_suffix("")
    parts = tuple(module_path.parts)

    doc_path = module_path.with_suffix(".md")
    full_doc_path = Path("reference", doc_path)

    if parts[-1] == "__init__":
        parts = parts[:-1]
        doc_path = doc_path.with_name("index.md")
        full_doc_path = full_doc_path.with_name("index.md")

    _nav[parts] = doc_path.as_posix()

    with mkdocs_gen_files.open(full_doc_path, "w") as doc_file:
        identifier = ".".join(parts)
        doc_file.write(f"# `{identifier}`\n\n::: {identifier}\n")

    mkdocs_gen_files.set_edit_path(full_doc_path, path.relative_to(_ROOT))


for module in _PUBLIC_MODULES:
    if module.name != "__init__.py" and module.name.startswith("_"):
        continue
    _document(module)

with mkdocs_gen_files.open("reference/SUMMARY.md", "w") as nav_file:
    nav_file.writelines(_nav.build_literate_nav())
