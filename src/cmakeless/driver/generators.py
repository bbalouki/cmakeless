"""CMake generator selection: a small Strategy behind one factory function."""

from __future__ import annotations

import shutil
from dataclasses import dataclass

from cmakeless.errors import ConfigurationError


@dataclass(frozen=True, slots=True)
class Generator:
    """A choice of CMake generator, expressed as extra configure arguments.

    Attributes:
        name: The user-facing generator name.
        cmake_args: Arguments appended to the cmake configure command;
            empty means CMake picks its own default.
    """

    name: str
    cmake_args: tuple[str, ...]


_NINJA = Generator(name="ninja", cmake_args=("-G", "Ninja"))
# CMake's default on Windows already picks the newest installed Visual Studio,
# so the Visual Studio strategy delegates rather than hard-coding a year.
_VISUAL_STUDIO = Generator(name="vs", cmake_args=())
_DEFAULT = Generator(name="default", cmake_args=())

_KNOWN_GENERATORS = ("ninja", "vs")


def select_generator(name: str | None) -> Generator:
    """Resolve a user-facing generator name to a strategy.

    Any name that is not a known shorthand is passed to CMake verbatim, so
    every generator CMake supports stays reachable.

    Args:
        name: "ninja", "vs", a raw CMake generator name, or None to
            auto-select (Ninja when available, otherwise CMake's default).

    Returns:
        The resolved generator strategy.

    Raises:
        ConfigurationError: When Ninja is requested explicitly but is not
            on PATH.
    """
    if name is None:
        return _NINJA if shutil.which("ninja") is not None else _DEFAULT
    normalized = name.strip().lower()
    if normalized == "ninja":
        if shutil.which("ninja") is None:
            raise ConfigurationError(
                "The Ninja generator was requested but 'ninja' is not on PATH. "
                "Install it from https://ninja-build.org/ (or your package "
                "manager), or drop --generator to let CMake pick a default."
            )
        return _NINJA
    if normalized in ("vs", "visual-studio", "visual_studio"):
        return _VISUAL_STUDIO
    return Generator(name=name, cmake_args=("-G", name))


def known_generator_names() -> tuple[str, ...]:
    """List the generator shorthands the CLI documents.

    Returns:
        The shorthand names accepted by --generator.
    """
    return _KNOWN_GENERATORS
