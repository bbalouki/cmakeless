# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""CMakeGlobals: every CMake variable a real configure defines, as attributes.

Created via Project.cmake_globals(); the probe runs immediately (never a
hand-written CMake-language parser), so hasattr(cmake, "ANDROID") and similar
checks are usable while the build description is still being written.
"""

from __future__ import annotations

from collections.abc import Mapping


class CMakeGlobals:
    """Every CMake variable a throwaway configure discovered, as attributes.

    hasattr(result, name) mirrors CMake's if(DEFINED name), not if(name): a
    variable CMake never sets on this platform/toolchain (ANDROID, IOS, ...)
    is simply absent, not present-and-false. This is deliberate, not a
    compromise: those variables are only ever set by CMake itself on a
    matching platform or toolchain, so hasattr(cmake, "ANDROID") is true
    exactly when an Android toolchain configured this probe. Every value is
    the raw string CMake resolved it to; coerce booleans yourself the way
    CMake's own if() would (ON/TRUE/Y/YES/1, case-insensitively, are true).
    """

    def __init__(self, values: Mapping[str, str]) -> None:
        """Wrap one throwaway configure's discovered variables.

        Args:
            values: Every variable CMake reported, name to resolved value.
        """
        self._values = dict(values)

    def __getattr__(self, name: str) -> str:
        """Look up a discovered variable by attribute access.

        Args:
            name: The CMake variable name; matched exactly (CMake variable
                names are case-sensitive).

        Returns:
            The variable's resolved value.

        Raises:
            AttributeError: When CMake never defined ``name``; this is what
                makes hasattr(result, name) mean if(DEFINED name).
        """
        try:
            return self._values[name]
        except KeyError:
            raise AttributeError(
                f"CMakeGlobals has no variable named {name!r}: CMake never "
                f"defined it for this probe. Use hasattr(cmake, {name!r}) to "
                f"check first, or .get({name!r}, default) for a fallback."
            ) from None

    def __contains__(self, name: str) -> bool:
        """True when CMake defined ``name``.

        Args:
            name: The CMake variable name.

        Returns:
            True when the variable was discovered.
        """
        return name in self._values

    def get(self, name: str, default: str | None = None) -> str | None:
        """Look up a discovered variable without raising when it is unset.

        Args:
            name: The CMake variable name.
            default: Returned when CMake never defined ``name``.

        Returns:
            The variable's resolved value, or ``default``.
        """
        return self._values.get(name, default)

    def __repr__(self) -> str:
        """Developer-facing representation.

        Returns:
            The number of discovered variables.
        """
        return f"CMakeGlobals({len(self._values)} variables)"
