"""The Option builder: a typed CMake cache variable, returned by Project.option().

Users create Options via Project.option(); the handle is usable in
When.option(...) conditions and in Preset(options={...}).
"""

from __future__ import annotations

from cmakeless.errors import ConfigurationError
from cmakeless.model.nodes import OptionModel, OptionType


class Option:
    """A typed CMake cache variable/option.

    Attributes:
        name: The option's CMake cache-variable name (read-only property).
    """

    def __init__(
        self,
        name: str,
        *,
        default: bool | int | str,
        help: str = "",
        type: type[bool] | type[int] | type[str] | None = None,
        script: str,
    ) -> None:
        """Describe a project option.

        Args:
            name: The cache-variable name, for example "MYLIB_BUILD_GUI".
            default: The default value.
            help: Shown by cmake-gui/ccmake and the 'cmakeless options' verb.
            type: bool, int, or str; inferred from default when omitted.
            script: Display name of the owning build description, used in
                error messages.

        Raises:
            ConfigurationError: When neither ``type`` nor ``default`` names
                a supported cache-variable type.
        """
        value_type = _resolve_option_type(default, type, name=name, script=script)
        self._model = OptionModel(name=name, default=default, value_type=value_type, help=help)

    @property
    def name(self) -> str:
        """The option's CMake cache-variable name."""
        return self._model.name

    def __repr__(self) -> str:
        """Developer-facing representation.

        Returns:
            The name and default value of this option.
        """
        return f"Option(name={self._model.name!r}, default={self._model.default!r})"

    def _freeze(self) -> OptionModel:
        """Hand out the frozen model node.

        Returns:
            The OptionModel; validation happens on the frozen project.
        """
        return self._model


def _resolve_option_type(
    default: bool | int | str,
    type_: type[bool] | type[int] | type[str] | None,
    *,
    name: str,
    script: str,
) -> OptionType:
    """Infer or validate the option's CMake cache type.

    bool is checked before int (and before ``type_ is None``'s isinstance
    fallback) because bool is an int subclass in Python.

    Args:
        default: The option's default value.
        type_: The explicit type override, or None to infer from default.
        name: The option's name, for error messages.
        script: Display name of the owning build description, for messages.

    Returns:
        The matching OptionType.

    Raises:
        ConfigurationError: When neither ``type_`` nor ``default`` names a
            supported cache-variable type.
    """
    if type_ is bool or (type_ is None and isinstance(default, bool)):
        return OptionType.BOOL
    if type_ is int or (type_ is None and isinstance(default, int)):
        return OptionType.INT
    if type_ is str or (type_ is None and isinstance(default, str)):
        return OptionType.STRING
    raise ConfigurationError(
        f"Option {name!r} in {script} has default={default!r} of an unsupported "
        f"type. Pass type=bool, type=int, or type=str explicitly."
    )
