"""Codified code standards, enforced by CI.

Two rules from the project's engineering guidelines:

- Every module, class, function, and method carries a docstring (the
  library documents parameters and return values too; tests need at least
  a description).
- Every function and method body stays under 35 lines of code, its own
  docstring excluded.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MAX_FUNCTION_CODE_LINES = 35

type _Definition = ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef


def _python_files(directory: str) -> list[Path]:
    """List every Python file under a top-level repository directory."""
    return sorted((REPO_ROOT / directory).rglob("*.py"))


def _definitions(tree: ast.Module) -> list[_Definition]:
    """Collect every class, function, and method definition in a module."""
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
    ]


def _code_line_count(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Count a function's lines from `def` to end, its own docstring excluded."""
    assert node.end_lineno is not None
    span = node.end_lineno - node.lineno + 1
    first = node.body[0]
    is_docstring = (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
    )
    if is_docstring:
        assert first.end_lineno is not None
        span -= first.end_lineno - first.lineno + 1
    return span


@pytest.mark.parametrize(
    "path", _python_files("src") + _python_files("tests"), ids=lambda path: path.name
)
def test_every_definition_has_a_docstring(path: Path) -> None:
    """Every definition has a docstring."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    undocumented = [
        f"{path.name}:{node.lineno} {node.name}"
        for node in _definitions(tree)
        if ast.get_docstring(node) is None
    ]
    if ast.get_docstring(tree) is None:
        undocumented.insert(0, f"{path.name}:1 (module)")
    assert not undocumented, f"missing docstrings: {', '.join(undocumented)}"


@pytest.mark.parametrize(
    "path", _python_files("src") + _python_files("tests"), ids=lambda path: path.name
)
def test_every_function_is_under_the_line_limit(path: Path) -> None:
    """Every function is under the line limit."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    oversized = [
        f"{path.name}:{node.lineno} {node.name} ({_code_line_count(node)} lines)"
        for node in _definitions(tree)
        if not isinstance(node, ast.ClassDef) and _code_line_count(node) >= MAX_FUNCTION_CODE_LINES
    ]
    assert not oversized, f"functions over {MAX_FUNCTION_CODE_LINES} lines: {', '.join(oversized)}"
