"""Plugin extensions that contribute CMake to a target, fenced with their origin.

An extension is any object with a ``version`` string and an ``emit(target,
options)`` method returning CMake text. Installed distributions publish them
under the "cmakeless.extensions" entry-point group; register_extension()
adds one explicitly, and an explicit registration always wins.
"""

from __future__ import annotations

import importlib.metadata
from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from cmakeless.errors import ConfigurationError

EXTENSION_ENTRY_POINT_GROUP = "cmakeless.extensions"
TOOLCHAIN_ENTRY_POINT_GROUP = "cmakeless.toolchains"
TEMPLATE_ENTRY_POINT_GROUP = "cmakeless.templates"


@runtime_checkable
class Extension(Protocol):
    """What a plugin extension provides.

    Attributes:
        version: The plugin's version, written into the generated fence so a
            reader knows exactly which plugin produced the lines.
    """

    version: str

    def emit(self, target: str, options: Mapping[str, object]) -> str:
        """Produce the CMake this extension contributes to one target.

        Args:
            target: The CMake target name the snippet applies to.
            options: The keyword arguments the user passed to extend().

        Returns:
            CMake text, emitted verbatim after the target's own settings.
        """
        ...


_EXTENSIONS: dict[str, Extension] = {}


def register_extension(name: str, extension: Extension) -> None:
    """Make an extension available to target.extend(name) in this process.

    Args:
        name: The name build descriptions refer to it by.
        extension: The extension object.

    Raises:
        ConfigurationError: When the object does not provide version and
            emit().
    """
    if not isinstance(extension, Extension):
        raise ConfigurationError(
            f"register_extension({name!r}, ...) needs an object with a 'version' "
            f"string and an 'emit(target, options)' method returning CMake text."
        )
    _EXTENSIONS[name] = extension


def load_extension(name: str) -> Extension:
    """Find an extension by name: explicit registrations first, then plugins.

    Args:
        name: The extension name.

    Returns:
        The extension object.

    Raises:
        ConfigurationError: When no registration or installed plugin has it.
    """
    if name in _EXTENSIONS:
        return _EXTENSIONS[name]
    for entry_point in importlib.metadata.entry_points(group=EXTENSION_ENTRY_POINT_GROUP):
        if entry_point.name == name:
            loaded = entry_point.load()
            extension = loaded() if isinstance(loaded, type) else loaded
            register_extension(name, extension)
            return _EXTENSIONS[name]
    raise ConfigurationError(
        f"No extension named {name!r}. Install the plugin that provides it (it "
        f'publishes an entry point in the "{EXTENSION_ENTRY_POINT_GROUP}" group), or '
        f"call cmakeless.register_extension({name!r}, ...) first."
    )
