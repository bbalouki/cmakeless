"""Every layer package re-exports its submodules' public surface.

The four layer packages each promise in their docstring that importing from
the package reaches the whole layer. That promise silently rots whenever a
new public name is added to a submodule, so it is checked here instead.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path
from types import ModuleType

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "src" / "cmakeless"
SUBPACKAGES = ("api", "deps", "driver", "emitter", "model")

# Names deliberately re-exported under a different spelling, because the bare
# name would be ambiguous outside its own module.
EXPORT_ALIASES = {"cmakeless.deps.registry.register": "register_dependency"}


def _defined_public_names(path: Path) -> list[str]:
    """Public module-level names a module defines itself, ignoring re-imports."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            names.append(node.name)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.append(node.target.id)
        elif isinstance(node, ast.TypeAlias) and isinstance(node.name, ast.Name):
            names.append(node.name.id)
        elif isinstance(node, ast.Assign):
            names.extend(t.id for t in node.targets if isinstance(t, ast.Name))
    return [name for name in names if not name.startswith("_")]


def _submodules(package: str) -> list[Path]:
    """Every public module file inside one layer package."""
    return sorted(p for p in (PACKAGE_ROOT / package).glob("*.py") if not p.stem.startswith("_"))


def _exported(package: str) -> tuple[ModuleType, set[str]]:
    """A layer package and the set of names it re-exports."""
    module = importlib.import_module(f"cmakeless.{package}")
    return module, set(module.__all__)


@pytest.mark.parametrize("package", SUBPACKAGES)
def test_package_reexports_every_public_submodule_name(package: str) -> None:
    """Package reexports every public submodule name."""
    _, exported = _exported(package)
    missing: list[str] = []
    for path in _submodules(package):
        for name in _defined_public_names(path):
            alias = EXPORT_ALIASES.get(f"cmakeless.{package}.{path.stem}.{name}", name)
            if alias not in exported:
                missing.append(f"{path.name}:{name}")
    assert not missing, (
        f"cmakeless.{package}.__all__ omits public names: {', '.join(missing)}. "
        f"Re-export them or make them private with a leading underscore."
    )


@pytest.mark.parametrize("package", SUBPACKAGES)
def test_every_exported_name_resolves(package: str) -> None:
    """Every exported name resolves."""
    module, exported = _exported(package)
    unresolved = [name for name in sorted(exported) if not hasattr(module, name)]
    assert not unresolved, f"cmakeless.{package}.__all__ names nothing: {', '.join(unresolved)}"


def test_public_package_exports_resolve() -> None:
    """Public package exports resolve."""
    import cmakeless

    unresolved = [name for name in cmakeless.__all__ if not hasattr(cmakeless, name)]
    assert not unresolved, f"cmakeless.__all__ names nothing: {', '.join(unresolved)}"
    duplicates = sorted({n for n in cmakeless.__all__ if cmakeless.__all__.count(n) > 1})
    assert not duplicates, f"cmakeless.__all__ repeats: {', '.join(duplicates)}"


def test_underscore_modules_publish_through_the_package() -> None:
    """Underscore modules publish through the package."""
    import cmakeless

    exported = set(cmakeless.__all__)
    missing: list[str] = []
    for path in sorted(PACKAGE_ROOT.glob("_*.py")):
        if path.stem == "__init__":
            continue
        missing.extend(
            f"{path.name}:{name}" for name in _defined_public_names(path) if name not in exported
        )
    assert not missing, (
        f"cmakeless.__all__ omits public names defined in private modules: "
        f"{', '.join(missing)}. Users must never import from a submodule, so re-export "
        f"them or make them private with a leading underscore."
    )
