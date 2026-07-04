# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""CMake generator selection: a small Strategy behind one factory function."""

from __future__ import annotations

import enum
import shutil
from dataclasses import dataclass

from cmakeless.errors import ConfigurationError


class GeneratorFamily(enum.Enum):
    """Which build-tool family a generator produces, for launcher wiring.

    Attributes:
        MAKEFILES: Unix Makefiles.
        NINJA: Single-config Ninja.
        NINJA_MULTI_CONFIG: Ninja Multi-Config.
        VISUAL_STUDIO: Any Visual Studio generator.
        XCODE: The Xcode generator.
        OTHER: Anything else (raw generator names CMakeless cannot classify).
    """

    MAKEFILES = "makefiles"
    NINJA = "ninja"
    NINJA_MULTI_CONFIG = "ninja-multi-config"
    VISUAL_STUDIO = "visual-studio"
    XCODE = "xcode"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class Generator:
    """A choice of CMake generator, expressed as extra configure arguments.

    Attributes:
        name: The user-facing generator name.
        cmake_args: Arguments appended to the cmake configure command;
            empty means CMake picks its own default.
        family: Which build-tool family this generator produces, so the
            driver knows where a compiler-cache launcher actually works.
    """

    name: str
    cmake_args: tuple[str, ...]
    family: GeneratorFamily = GeneratorFamily.OTHER


_NINJA = Generator(name="ninja", cmake_args=("-G", "Ninja"), family=GeneratorFamily.NINJA)
_NINJA_MULTI_CONFIG = Generator(
    name="ninja-multi",
    cmake_args=("-G", "Ninja Multi-Config"),
    family=GeneratorFamily.NINJA_MULTI_CONFIG,
)
_MAKEFILES = Generator(
    name="make", cmake_args=("-G", "Unix Makefiles"), family=GeneratorFamily.MAKEFILES
)
_XCODE = Generator(name="xcode", cmake_args=("-G", "Xcode"), family=GeneratorFamily.XCODE)
# CMake's default on Windows already picks the newest installed Visual Studio,
# so the Visual Studio strategy delegates rather than hard-coding a year.
_VISUAL_STUDIO = Generator(name="vs", cmake_args=(), family=GeneratorFamily.VISUAL_STUDIO)
_DEFAULT = Generator(name="default", cmake_args=())

_KNOWN_GENERATORS = ("ninja", "ninja-multi", "make", "vs", "xcode")

# Substring markers used to infer a raw -G name's family, so a user who types
# a full CMake generator name (not one of our shorthands) still gets correct
# cache-launcher wiring. Checked in order; multi-config Ninja must be tested
# before plain Ninja since "Ninja Multi-Config" also contains "ninja".
_FAMILY_MARKERS: tuple[tuple[str, GeneratorFamily], ...] = (
    ("ninja multi-config", GeneratorFamily.NINJA_MULTI_CONFIG),
    ("ninja", GeneratorFamily.NINJA),
    ("makefiles", GeneratorFamily.MAKEFILES),
    ("visual studio", GeneratorFamily.VISUAL_STUDIO),
    ("xcode", GeneratorFamily.XCODE),
)


def select_generator(name: str | None) -> Generator:
    """Resolve a user-facing generator name to a strategy.

    Any name that is not a known shorthand is passed to CMake verbatim, so
    every generator CMake supports stays reachable.

    Args:
        name: "ninja", "ninja-multi", "make", "vs", "xcode", a raw CMake
            generator name, or None to auto-select (Ninja when available,
            otherwise CMake's default).

    Returns:
        The resolved generator strategy.

    Raises:
        ConfigurationError: When Ninja (or Ninja Multi-Config) is requested
            explicitly but 'ninja' is not on PATH.
    """
    if name is None:
        return _NINJA if shutil.which("ninja") is not None else _DEFAULT
    normalized = name.strip().lower()
    if normalized in ("ninja", "ninja-multi", "ninja-multi-config"):
        return _select_ninja_family(normalized)
    if normalized in ("make", "unix-makefiles", "makefiles"):
        return _MAKEFILES
    if normalized in ("vs", "visual-studio", "visual_studio"):
        return _VISUAL_STUDIO
    if normalized == "xcode":
        return _XCODE
    return Generator(name=name, cmake_args=("-G", name), family=_infer_family(name))


def _select_ninja_family(normalized: str) -> Generator:
    """Resolve a Ninja shorthand, checking that 'ninja' itself is on PATH.

    Args:
        normalized: The lowercased, stripped shorthand: "ninja",
            "ninja-multi", or "ninja-multi-config".

    Returns:
        The single-config or multi-config Ninja generator.

    Raises:
        ConfigurationError: When 'ninja' is not on PATH.
    """
    if shutil.which("ninja") is None:
        raise ConfigurationError(
            "The Ninja generator was requested but 'ninja' is not on PATH. "
            "Install it from https://ninja-build.org/ (or your package "
            "manager), or drop --generator to let CMake pick a default."
        )
    return _NINJA if normalized == "ninja" else _NINJA_MULTI_CONFIG


def _infer_family(name: str) -> GeneratorFamily:
    """Guess a raw -G generator name's family from a substring match.

    Args:
        name: The raw generator name passed straight to CMake's -G flag.

    Returns:
        The matching family, or OTHER when nothing matches.
    """
    normalized = name.strip().lower()
    for marker, family in _FAMILY_MARKERS:
        if marker in normalized:
            return family
    return GeneratorFamily.OTHER


def known_generator_names() -> tuple[str, ...]:
    """List the generator shorthands the CLI documents.

    Returns:
        The shorthand names accepted by --generator.
    """
    return _KNOWN_GENERATORS
