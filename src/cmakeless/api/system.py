"""Typed link targets for things that are not this project's own libraries.

`target.link()` accepts these alongside a `Library`, so linking the thread
library, a Windows system DLL, or an Apple framework never needs raw CMake.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from cmakeless.errors import ConfigurationError
from cmakeless.model.nodes import LinkKind

# A bare library name the linker resolves itself: no path separators, no
# flags, no generator expressions, so it can never smuggle in other options.
_LIBRARY_NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.+-]*$")

# An imported target is always namespaced, which is how CMake itself tells
# it apart from a plain library name.
_IMPORTED_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.+-]*::[A-Za-z_][A-Za-z0-9_.+-]*$")


@dataclass(frozen=True, slots=True)
class SystemLibrary:
    """A link target outside this project, validated at construction.

    Built through the System factories or Imported(); never constructed
    directly with an arbitrary kind.

    Attributes:
        name: The library, framework, or imported-target name.
        kind: What the name refers to.
    """

    name: str
    kind: LinkKind

    def __str__(self) -> str:
        """User-facing representation.

        Returns:
            The name exactly as the linker or CMake will see it.
        """
        return self.name


class System:
    """Factories for the platform's own libraries."""

    @staticmethod
    def threads() -> SystemLibrary:
        """The platform thread library (pthread on POSIX, nothing on Windows).

        Returns:
            A link target that emits find_package(Threads) and links
            Threads::Threads.
        """
        return SystemLibrary(name="Threads::Threads", kind=LinkKind.THREADS)

    @staticmethod
    def library(name: str) -> SystemLibrary:
        """A bare operating-system library the linker finds on its own.

        Args:
            name: The library name without prefix or suffix, for example
                "ws2_32", "dl", or "rt".

        Returns:
            A link target naming that library.

        Raises:
            ConfigurationError: When the name is a path, a flag, or empty.
        """
        if not _LIBRARY_NAME.match(name):
            raise ConfigurationError(
                f"System.library({name!r}) is not a bare library name. Pass the "
                f'name the linker searches for, for example "ws2_32" or "dl", '
                f"not a path or a flag; use link_options() for linker flags."
            )
        return SystemLibrary(name=name, kind=LinkKind.SYSTEM)

    @staticmethod
    def framework(name: str) -> SystemLibrary:
        """An Apple framework, linked only when building for an Apple platform.

        Args:
            name: The framework name, for example "Metal" or "Cocoa".

        Returns:
            A link target that is a no-op on every non-Apple platform.

        Raises:
            ConfigurationError: When the name is not a bare framework name.
        """
        if not _LIBRARY_NAME.match(name):
            raise ConfigurationError(
                f"System.framework({name!r}) is not a framework name. Pass the "
                f'bare name, for example "Metal", without ".framework" or a path.'
            )
        return SystemLibrary(name=name, kind=LinkKind.FRAMEWORK)


def Imported(name: str) -> SystemLibrary:
    """Name an imported target some find_package() or subproject provides.

    Args:
        name: The namespaced target, for example "Vulkan::Vulkan".

    Returns:
        A link target naming that imported target.

    Raises:
        ConfigurationError: When the name is not namespaced with '::'.
    """
    if not _IMPORTED_NAME.match(name):
        raise ConfigurationError(
            f"Imported({name!r}) is not a namespaced imported target. CMake "
            f'imported targets look like "Vulkan::Vulkan"; for a plain system '
            f'library use System.library("{name}"), and for a package use '
            f'target.depends("{name.lower()}/<version>").'
        )
    return SystemLibrary(name=name, kind=LinkKind.IMPORTED)
