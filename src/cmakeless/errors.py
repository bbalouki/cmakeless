"""The CMakeless exception hierarchy.

Errors are a feature: every message raised on purpose must say three things.
What went wrong, where (file and target), and what to try next.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """One parsed error from cmake or compiler output.

    Attributes:
        file: Path of the offending file as printed by the tool, or None when
            the tool gave no location (linker errors, for example).
        line: 1-based line number within ``file``, or None when unknown.
        message: The error text with the location prefix stripped.
    """

    file: str | None
    line: int | None
    message: str

    def __str__(self) -> str:
        """Render the diagnostic as ``file:line: message`` when located.

        Returns:
            The message, prefixed with ``file:line:`` when both are known.
        """
        location = f"{self.file}:{self.line}: " if self.file and self.line else ""
        return f"{location}{self.message}"


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

    Attributes:
        command: The exact argument vector that was executed.
        exit_code: The subprocess exit code (never zero).
        log_path: Path to the persisted full output, or None if logging the
            output itself failed.
        diagnostics: Structured errors parsed from the output, first error
            first; may be empty when nothing recognizable was found.
    """

    def __init__(
        self,
        message: str,
        *,
        command: Sequence[str],
        exit_code: int,
        log_path: Path | None = None,
        diagnostics: Sequence[Diagnostic] = (),
    ) -> None:
        """Store the failure context alongside the human-readable message.

        Args:
            message: Complete user-facing explanation (what, where, next).
            command: The exact argument vector that was executed.
            exit_code: The subprocess exit code (never zero).
            log_path: Path to the persisted full output, if any.
            diagnostics: Structured errors parsed from the output.
        """
        super().__init__(message)
        self.command: tuple[str, ...] = tuple(command)
        self.exit_code: int = exit_code
        self.log_path: Path | None = log_path
        self.diagnostics: tuple[Diagnostic, ...] = tuple(diagnostics)
