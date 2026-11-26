"""Per-target settings shared by every target builder.

A mixin, so the target builders keep their own module small while every
kind (executable, library, test, Python module) gains the same vocabulary.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from cmakeless.api.cpu import Cpu
from cmakeless.api.extensions import load_extension
from cmakeless.api.profiles import Profile
from cmakeless.errors import ConfigurationError
from cmakeless.model.properties import ExtensionUseModel, QtModel, TargetPropertiesModel

# The Qt major versions use_qt() knows how to find.
_QT_MAJORS = frozenset({5, 6})


class _TargetSettings:
    """Output, ABI, platform, and tooling settings for one target.

    Attributes:
        c_std: This target's C standard, overriding the project's; None to
            inherit it.
        output_name: The built file's base name, or None for the target name.
        visibility: "hidden" or "default" symbol visibility, or None for the
            compiler default.
        gui: True for a windowed application rather than a console one.
        msvc_runtime: "static" or "dynamic" MSVC runtime library, or None.
        linker_script: A project-relative linker script, or None.
        map_file: True to write a linker map file next to the binary.
        cuda_architectures: CUDA architectures to build for, for example
            ["86"]; empty for the CMake default.
        cpu: The CPU this target is optimized for (see Cpu), or None.
        profile: This target's own profile, replacing the project's.
        warnings: This target's warning preset, replacing the project's.
        warnings_as_errors: True or False to override the project's
            setting for this target; None to inherit it.
    """

    _name: str
    _script: str

    def _init_settings(self, declared_line: int | None) -> None:
        """Start with every setting at its inherit-or-default value.

        Args:
            declared_line: The build-description line that declared the target.
        """
        self.c_std: int | None = None
        self.output_name: str | None = None
        self.visibility: str | None = None
        self.gui: bool = False
        self.msvc_runtime: str | None = None
        self.linker_script: str | None = None
        self.map_file: bool = False
        self.cuda_architectures: Sequence[str] = []
        self.cpu: Cpu | None = None
        self.profile: Profile | None = None
        self.warnings: str | None = None
        self.warnings_as_errors: bool | None = None
        self._post_build: list[tuple[str, ...]] = []
        self._qt: QtModel | None = None
        self._extensions: list[ExtensionUseModel] = []
        self._declared_line = declared_line

    @property
    def file(self) -> str:
        """The built file's path, as a reference CMake resolves at build time."""
        return f"$<TARGET_FILE:{self._name}>"

    @property
    def declared_line(self) -> int | None:
        """The build-description line that declared this target, if known."""
        return self._declared_line

    def post_build(self, *argv: str) -> None:
        """Run a command right after this target links, for example objcopy.

        Args:
            *argv: The argument vector, never a shell string; use
                target.file to name the built binary.

        Raises:
            ConfigurationError: When no command is given.
        """
        if not argv:
            raise ConfigurationError(
                f"post_build() on target {self._name!r} in {self._script} needs a "
                f'command, for example target.post_build("objcopy", "-O", "ihex", '
                f'target.file, "firmware.hex").'
            )
        self._post_build.append(tuple(argv))

    def use_qt(
        self, major: int = 6, *, components: Sequence[str], resources: Sequence[str] = ()
    ) -> None:
        """Build this target with Qt: moc, uic, and rcc run automatically.

        Args:
            major: The Qt major version, 5 or 6.
            components: Qt modules to link, for example ["Widgets", "Charts"].
            resources: Project-relative .qrc files compiled into the target.

        Raises:
            ConfigurationError: When the major version is unsupported or no
                component is named.
        """
        if major not in _QT_MAJORS or not components:
            raise ConfigurationError(
                f"use_qt({major}, components={list(components)!r}) on target "
                f"{self._name!r} in {self._script}: pass Qt 5 or 6 and at least "
                f'one component, for example use_qt(6, components=["Widgets"]).'
            )
        self._qt = QtModel(
            major=major,
            components=tuple(components),
            resources=tuple(Path(resource) for resource in resources),
        )

    def extend(self, name: str, **options: object) -> None:
        """Apply a plugin extension to this target.

        The extension runs now, so a bad option fails at this line; its
        CMake is emitted after the target's own settings, fenced with the
        extension's name and version.

        Args:
            name: The extension name (an installed plugin or a
                register_extension() call).
            **options: Passed to the extension unchanged.

        Raises:
            ConfigurationError: When no extension has that name, or it
                produced no CMake.
        """
        extension = load_extension(name)
        snippet = extension.emit(self._name, options)
        if not snippet.strip():
            raise ConfigurationError(
                f"Extension {name!r} produced no CMake for target {self._name!r} in "
                f"{self._script}. Check its options."
            )
        self._extensions.append(
            ExtensionUseModel(name=name, version=extension.version, snippet=snippet)
        )

    def _qt_link_targets(self) -> tuple[str, ...]:
        """The imported Qt targets use_qt() implies.

        Returns:
            One QtN::Component per requested component, or nothing.
        """
        if self._qt is None:
            return ()
        return tuple(f"Qt{self._qt.major}::{component}" for component in self._qt.components)

    def _freeze_properties(
        self, *, version: str | None, soversion: str | None
    ) -> TargetPropertiesModel:
        """Freeze every setting into the model's properties node.

        Args:
            version: A shared library's full ABI version, or None.
            soversion: A shared library's compatibility version, or None.

        Returns:
            The frozen properties; validation happens on the model.
        """
        return TargetPropertiesModel(
            c_std=self.c_std,
            output_name=self.output_name,
            version=version,
            soversion=soversion,
            visibility=self.visibility,
            gui=self.gui,
            msvc_runtime=self.msvc_runtime,
            linker_script=Path(self.linker_script) if self.linker_script is not None else None,
            map_file=self.map_file,
            post_build=tuple(self._post_build),
            cuda_architectures=tuple(self.cuda_architectures),
            cpu=self.cpu._freeze() if self.cpu is not None else None,
            profile=self.profile._freeze() if self.profile is not None else None,
            warnings=self.warnings,
            warnings_as_errors=self.warnings_as_errors,
            qt=self._qt,
            extensions=tuple(self._extensions),
            declared_line=self._declared_line,
        )
