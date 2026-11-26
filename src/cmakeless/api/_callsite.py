"""Locate the user's build description on the call stack."""

from __future__ import annotations

import inspect
from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent


def calling_frame() -> tuple[Path, int] | None:
    """Find the first stack frame outside the cmakeless package.

    Walking the stack keeps a project's root and each target's declaration
    line tied to the build description, not the process working directory.

    Returns:
        The (absolute script path, line number) of that frame, or None when
        every frame is internal (a REPL or an embedding host).
    """
    for frame_info in inspect.stack():
        filename = frame_info.filename
        if not filename or filename.startswith("<"):
            continue
        candidate = Path(filename).resolve()
        if not candidate.is_relative_to(_PACKAGE_ROOT):
            return (candidate, frame_info.lineno)
    return None
