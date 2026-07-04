# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""The Preset builder: a named configuration bundle mapped onto CMake presets.

Users create Presets and register them with project.add_preset(); the emitter
turns them into CMakePresets.json so IDEs and 'cmakeless build --preset name'
pick them up natively.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from cmakeless.model.nodes import PresetModel

if TYPE_CHECKING:
    from cmakeless.api.toolchains import Toolchain


class Preset:
    """A named bundle of configuration: build type, sanitizers, LTO, toolchain.

    Attributes:
        name: The preset name (read-only property).
    """

    def __init__(
        self,
        name: str,
        *,
        optimize: str = "debug",
        sanitize: Sequence[str] = (),
        lto: bool = False,
        toolchain: str | Toolchain | None = None,
        options: Mapping[str, bool | int | str] | None = None,
        env: Mapping[str, str] | None = None,
        inherits: str | Preset | None = None,
    ) -> None:
        """Describe a preset.

        Args:
            name: The preset name, shown by IDEs and passed to --preset.
            optimize: Optimization level ("none", "debug", "release",
                "relwithdebinfo", or "minsize").
            sanitize: Sanitizer names this preset applies to every target.
            lto: True to enable interprocedural optimization.
            toolchain: A registered toolchain (or its name) to configure
                with, or None for the host toolchain.
            options: Cache-variable overrides for this preset's declared
                project.option()s, for example {"MYLIB_BUILD_GUI": False}.
            env: Environment variables set for this preset's configure,
                build, and test steps.
            inherits: Another preset (or its name) this preset inherits
                unset settings from.
        """
        self._name = name
        self._optimize = optimize
        self._sanitize = tuple(sanitize)
        self._lto = lto
        self._toolchain = toolchain if isinstance(toolchain, str | None) else toolchain.name
        self._options: dict[str, bool | int | str] = dict(options) if options is not None else {}
        self._env: dict[str, str] = dict(env) if env is not None else {}
        self._inherits = inherits if isinstance(inherits, str | None) else inherits.name

    @property
    def name(self) -> str:
        """The preset name, shown by IDEs and passed to --preset."""
        return self._name

    def __repr__(self) -> str:
        """Developer-facing representation.

        Returns:
            The name and settings of this preset.
        """
        return (
            f"Preset(name={self._name!r}, optimize={self._optimize!r}, "
            f"sanitize={list(self._sanitize)!r}, lto={self._lto!r}, "
            f"toolchain={self._toolchain!r}, options={self._options!r}, "
            f"env={self._env!r}, inherits={self._inherits!r})"
        )

    def _freeze(self) -> PresetModel:
        """Freeze this builder into its immutable model node.

        Returns:
            The PresetModel; validation happens on the frozen project.
        """
        return PresetModel(
            name=self._name,
            optimize=self._optimize,
            sanitize=tuple(sorted(set(self._sanitize))),
            lto=self._lto,
            toolchain=self._toolchain,
            options=tuple(sorted(self._options.items())),
            env=tuple(sorted(self._env.items())),
            inherits=self._inherits,
        )
