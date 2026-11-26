"""Quoting user-supplied text so CMake's parser reads it as exactly one argument."""

from __future__ import annotations


def quote_argument(token: str) -> str:
    """Render one string as a single quoted CMake argument.

    Backslashes and quotes are escaped so a Windows path or an argument
    containing a quote cannot end the argument early or be read as a CMake
    escape sequence. Dollar signs are deliberately left alone, so a caller
    can still pass a reference such as ${CMAKE_COMMAND} and have CMake
    expand it.

    Args:
        token: The argument text.

    Returns:
        The argument, escaped and wrapped in double quotes.
    """
    escaped = token.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
