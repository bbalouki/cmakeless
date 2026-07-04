# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""The When condition object: a closed, composable build-time predicate.

Construct via the factory classmethods (platform, compiler, config, option)
and compose with & (and), | (or), ~ (not). The emitter renders the same
WhenModel differently depending on where it is used (see
emitter/when_emitter.py); users never choose the mechanism.
"""

from __future__ import annotations

from cmakeless.api.options import Option
from cmakeless.errors import ConfigurationError
from cmakeless.model.nodes import (
    BUILD_TYPE_BY_OPTIMIZE,
    CMAKE_COMPILER_ID_BY_CANONICAL,
    CMAKE_PLATFORM_ID_BY_TOKEN,
    COMPILERS_BY_TOKEN,
    WhenKind,
    WhenModel,
)

# The CMake config names When.config() accepts, derived from the same
# build-type vocabulary presets and project.optimize already use.
_CMAKE_CONFIGS: frozenset[str] = frozenset(BUILD_TYPE_BY_OPTIMIZE.values())


class When:
    """A closed, composable build-time condition; combine with &, |, ~."""

    def __init__(self, model: WhenModel) -> None:
        """Wrap a frozen condition tree; use the factory classmethods instead.

        Args:
            model: The condition tree this value renders.
        """
        self._model = model

    @classmethod
    def platform(cls, *names: str) -> When:
        """Match when the target platform is any of the given names.

        Args:
            *names: "windows", "linux", or "macos".

        Returns:
            The platform condition.

        Raises:
            ConfigurationError: When a name is not one of the three.
        """
        return cls(WhenModel(kind=WhenKind.PLATFORM, names=_platform_ids(names)))

    @classmethod
    def compiler(cls, *names: str) -> When:
        """Match when the compiling toolchain is any of the given families.

        Args:
            *names: "gcc", "clang", "appleclang", or "msvc"; "gcc" also
                matches GNU-compatible compilers, "clang" matches both LLVM
                Clang and Apple Clang.

        Returns:
            The compiler condition.

        Raises:
            ConfigurationError: When a name is not a known compiler.
        """
        return cls(WhenModel(kind=WhenKind.COMPILER, names=_compiler_ids(names)))

    @classmethod
    def config(cls, *names: str) -> When:
        """Match when the active build configuration is any of the given names.

        Args:
            *names: "Debug", "Release", "RelWithDebInfo", or "MinSizeRel".

        Returns:
            The configuration condition.

        Raises:
            ConfigurationError: When a name is not a known CMake config.
        """
        return cls(WhenModel(kind=WhenKind.CONFIG, names=_config_names(names)))

    @classmethod
    def option(cls, option: str | Option, *, equals: bool | int | str = True) -> When:
        """Match when a declared project option equals the given value.

        Args:
            option: An Option handle from project.option(), or its name.
            equals: The value the option must equal; True/False for a bool
                option (the default), or the exact int/str value otherwise.

        Returns:
            The option condition.
        """
        name = option if isinstance(option, str) else option.name
        return cls(WhenModel(kind=WhenKind.OPTION, option_name=name, option_equals=equals))

    def __and__(self, other: When | Option) -> When:
        """Combine with another condition: true only when both are true.

        Args:
            other: Another condition, or an Option (sugar for
                When.option(other)).

        Returns:
            The combined condition.
        """
        return When(WhenModel(kind=WhenKind.AND, operands=(self._model, _as_when(other)._model)))

    def __or__(self, other: When | Option) -> When:
        """Combine with another condition: true when either is true.

        Args:
            other: Another condition, or an Option (sugar for
                When.option(other)).

        Returns:
            The combined condition.
        """
        return When(WhenModel(kind=WhenKind.OR, operands=(self._model, _as_when(other)._model)))

    def __invert__(self) -> When:
        """Negate this condition.

        Returns:
            The negated condition.
        """
        return When(WhenModel(kind=WhenKind.NOT, operands=(self._model,)))

    def __repr__(self) -> str:
        """Developer-facing representation.

        Returns:
            The condition's frozen model tree.
        """
        return f"When({self._model!r})"

    def _freeze(self) -> WhenModel:
        """Hand out the frozen model node (already immutable).

        Returns:
            The WhenModel this value wraps.
        """
        return self._model


def _as_when(value: When | Option) -> When:
    """Normalize a &/| operand: a bare Option is sugar for When.option().

    Args:
        value: The right-hand operand of & or |.

    Returns:
        The value itself, or When.option(value) when it is an Option.
    """
    return value if isinstance(value, When) else When.option(value)


def _platform_ids(names: tuple[str, ...]) -> tuple[str, ...]:
    """Translate friendly platform names into canonical CMake platform ids.

    Args:
        names: The user-supplied platform names.

    Returns:
        The matching $<PLATFORM_ID:...> values, in first-mention order.

    Raises:
        ConfigurationError: When a name is not a known platform.
    """
    resolved: list[str] = []
    for token in names:
        normalized = token.strip().lower()
        if normalized not in CMAKE_PLATFORM_ID_BY_TOKEN:
            known = ", ".join(sorted(CMAKE_PLATFORM_ID_BY_TOKEN))
            raise ConfigurationError(
                f"Unknown platform {token!r} in When.platform(...). Use one of: {known}."
            )
        value = CMAKE_PLATFORM_ID_BY_TOKEN[normalized]
        if value not in resolved:
            resolved.append(value)
    return tuple(resolved)


def _compiler_ids(names: tuple[str, ...]) -> tuple[str, ...]:
    """Translate friendly compiler names into canonical CMake compiler ids.

    Args:
        names: The user-supplied compiler names.

    Returns:
        The matching CXX_COMPILER_ID values, in first-mention order.

    Raises:
        ConfigurationError: When a name is not a known compiler.
    """
    canonical: list[str] = []
    for token in names:
        normalized = token.strip().lower()
        if normalized not in COMPILERS_BY_TOKEN:
            known = ", ".join(sorted(COMPILERS_BY_TOKEN))
            raise ConfigurationError(
                f"Unknown compiler {token!r} in When.compiler(...). Use one of: {known}."
            )
        canonical.extend(
            compiler for compiler in COMPILERS_BY_TOKEN[normalized] if compiler not in canonical
        )
    return tuple(CMAKE_COMPILER_ID_BY_CANONICAL[compiler] for compiler in canonical)


def _config_names(names: tuple[str, ...]) -> tuple[str, ...]:
    """Validate build-configuration names against CMake's known set.

    Args:
        names: The user-supplied configuration names.

    Returns:
        The names unchanged, deduplicated in first-mention order.

    Raises:
        ConfigurationError: When a name is not a known CMake configuration.
    """
    resolved: list[str] = []
    for name in names:
        if name not in _CMAKE_CONFIGS:
            known = ", ".join(sorted(_CMAKE_CONFIGS))
            raise ConfigurationError(
                f"Unknown build configuration {name!r} in When.config(...). Use one of: {known}."
            )
        if name not in resolved:
            resolved.append(name)
    return tuple(resolved)
