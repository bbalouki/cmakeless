"""The CMakeless exception hierarchy.

Errors are a feature: every message raised on purpose must say three things.
What went wrong, where (file and target), and what to try next.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path


class CmakelessError(Exception):
    """Base class for every error CMakeless raises on purpose."""


class ConfigurationError(CmakelessError):
    """The build description in build.py is invalid; caught at freeze time."""


class DependencyError(CmakelessError):
    """An external package cannot be resolved or fetched."""


class ToolchainError(CmakelessError):
    """A compiler or required tool is missing or misconfigured."""


class CMakeError(CmakelessError):
    """CMake itself failed.

    Carries the exact command line, the exit code, and the path to the full
    log so the failure can always be reproduced by hand.
    """

    def __init__(
        self,
        message: str,
        *,
        command: Sequence[str],
        exit_code: int,
        log_path: Path | None = None,
    ) -> None:
        super().__init__(message)
        self.command: tuple[str, ...] = tuple(command)
        self.exit_code: int = exit_code
        self.log_path: Path | None = log_path
