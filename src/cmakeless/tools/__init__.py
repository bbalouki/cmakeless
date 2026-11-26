"""Tools above the build description: importing CMake projects and templates.

This package re-exports every public name from its submodules, so
`from cmakeless.tools import ...` reaches the whole surface.
"""

from cmakeless.tools.importer import (
    IMPORT_BUILD_DIR,
    ImportResult,
    check_import,
    collapse_globs,
    compare_targets,
    import_project,
)
from cmakeless.tools.templates import (
    TEMPLATES,
    available_templates,
    render_template,
    write_template,
)

__all__ = [
    "IMPORT_BUILD_DIR",
    "TEMPLATES",
    "ImportResult",
    "available_templates",
    "check_import",
    "collapse_globs",
    "compare_targets",
    "import_project",
    "render_template",
    "write_template",
]
