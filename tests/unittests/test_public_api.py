"""The public API is frozen: a golden snapshot of every exported signature.

Since 1.0 the surface in cmakeless.__all__ is a Semantic Versioning promise,
so a change to it must be a deliberate, reviewed act rather than a side
effect. This snapshots the whole thing, the same way the emitter's output is
snapshotted, and fails when it drifts.

Regenerate deliberately, and only alongside a CHANGELOG entry:

    python -m tests.unittests.test_public_api
"""

from __future__ import annotations

import enum
import inspect
from pathlib import Path
from typing import Any

import cmakeless

GOLDEN = Path(__file__).parent / "golden" / "public_api.txt"


def _is_public(name: str) -> bool:
    """Tell whether a member name is part of the documented surface."""
    return not name.startswith("_") or name in {"__init__"}


def _signature(value: Any) -> str:
    """Render one callable's signature, or a placeholder when it has none."""
    try:
        return str(inspect.signature(value))
    except (TypeError, ValueError):
        return "(...)"


def _own_members(owner: type) -> dict[str, Any]:
    """Collect public members of a class and its CMakeless bases, nearest winning.

    Inherited members count: a target's add_sources() is just as public as
    the methods its own class defines, so dropping one from a shared base
    must fail here too.

    Bases from outside the package are skipped. What Exception or Protocol
    contributes is CPython's API, not ours, and its rendering moves between
    interpreter versions (BaseException.add_note reads as "add_note(...)"
    on 3.12 and "add_note(self, object, /)" on 3.13), which would make this
    snapshot fail on one Python and pass on another.
    """
    ours = [base for base in owner.__mro__ if base.__module__.split(".")[0] == "cmakeless"]
    collected: dict[str, Any] = {}
    for klass in reversed(ours):
        collected.update({n: v for n, v in vars(klass).items() if _is_public(n)})
    return collected


def _members(owner: type) -> list[str]:
    """Render every public method and property of one exported class."""
    lines: list[str] = []
    for name, value in sorted(_own_members(owner).items()):
        if isinstance(value, property):
            lines.append(f"    {name}: property")
        elif callable(value):
            lines.append(f"    {name}{_signature(value)}")
        else:
            lines.append(f"    {name}: {type(value).__name__}")
    return lines


def _render_class(name: str, value: type) -> list[str]:
    """Render one exported class: its header line and its members."""
    if issubclass(value, enum.Enum):
        return [f"class {name}(Enum)", *(f"    {member}" for member in value.__members__)]
    bases = ", ".join(base.__name__ for base in value.__bases__ if base is not object)
    header = f"class {name}({bases})" if bases else f"class {name}"
    return [header, *_members(value)]


def render_public_api() -> str:
    """Render the whole public surface as deterministic, diffable text.

    Returns:
        One block per name in cmakeless.__all__, sorted, newline-terminated.
    """
    lines: list[str] = []
    for name in sorted(cmakeless.__all__):
        value = getattr(cmakeless, name)
        if isinstance(value, type):
            lines.extend(_render_class(name, value))
        elif callable(value):
            lines.append(f"def {name}{_signature(value)}")
        else:
            lines.append(f"{name}: {type(value).__name__}")
        lines.append("")
    return "\n".join(lines)


def test_the_public_api_matches_the_golden_snapshot() -> None:
    """The public api matches the golden snapshot."""
    assert render_public_api() == GOLDEN.read_text(encoding="utf-8"), (
        "The public API changed. If that was deliberate, regenerate the snapshot with "
        "'python -m tests.unittests.test_public_api' and add a CHANGELOG entry saying "
        "what changed and why; breaking changes need a major version."
    )


if __name__ == "__main__":
    GOLDEN.write_text(render_public_api(), encoding="utf-8", newline="\n")
