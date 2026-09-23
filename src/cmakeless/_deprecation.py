"""One spelling for retiring public API, so every deprecation reads the same.

Since 1.0 nothing in the public surface may simply disappear: it is marked
here first, ships at least one more minor version emitting a warning that
names its replacement, and only then goes away. Keeping that mechanical is
what makes the versioning promise checkable rather than aspirational.
"""

from __future__ import annotations

import functools
import warnings
from collections.abc import Callable
from typing import Any, TypeVar

_Function = TypeVar("_Function", bound=Callable[..., Any])

_NOTE_TEMPLATE = ".. deprecated:: {removed_in}\n    Use {replacement} instead."


def deprecated(*, replacement: str, removed_in: str) -> Callable[[_Function], _Function]:
    """Mark a public function or method as deprecated.

    Args:
        replacement: What callers should use instead, spelled exactly as they
            would write it, for example "target.include_dirs()".
        removed_in: The version that will drop it, for example "2.0.0".

    Returns:
        A decorator that warns on call and otherwise changes nothing.
    """

    def decorate(function: _Function) -> _Function:
        """Wrap one function so calling it warns before it runs."""
        message = _deprecation_message(
            f"{function.__qualname__}()", replacement=replacement, removed_in=removed_in
        )

        @functools.wraps(function)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            """Warn, then call the deprecated function unchanged."""
            warnings.warn(message, DeprecationWarning, stacklevel=2)
            return function(*args, **kwargs)

        note = _NOTE_TEMPLATE.format(removed_in=removed_in, replacement=replacement)
        wrapper.__doc__ = f"{function.__doc__}\n\n{note}" if function.__doc__ else note
        return wrapper  # type: ignore[return-value]

    return decorate


def warn_deprecated_argument(name: str, *, owner: str, replacement: str, removed_in: str) -> None:
    """Warn that one argument of a still-supported call is deprecated.

    Call this only when the caller actually passed the argument, so a caller
    who has already migrated never sees a warning.

    Args:
        name: The deprecated argument's name.
        owner: The function or method that accepts it, for example
            "Project.add_library()".
        replacement: What to pass instead.
        removed_in: The version that will drop it.

    """
    message = _deprecation_message(
        f"The {name!r} argument of {owner}", replacement=replacement, removed_in=removed_in
    )
    warnings.warn(message, DeprecationWarning, stacklevel=3)


def _deprecation_message(subject: str, *, replacement: str, removed_in: str) -> str:
    """Compose the one message shape every deprecation warning uses.

    Args:
        subject: What is deprecated, as a sentence subject.
        replacement: What to use instead.
        removed_in: The version that will drop it.

    Returns:
        The warning text, naming the replacement and the removal version.
    """
    return (
        f"{subject} is deprecated and will be removed in cmakeless {removed_in}. "
        f"Use {replacement} instead."
    )
