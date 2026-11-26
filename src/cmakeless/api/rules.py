"""Typed clang-tidy rule sets for project.lint() and target.lint().

Each set is data: a list of clang-tidy checks that approximate a published
coding standard. They are a practical approximation, never a claim of
certified compliance; a qualified analysis tool is still required for
certification.
"""

from __future__ import annotations


class Rules:
    """A composable set of clang-tidy checks, passed as lint(clang_tidy=...)."""

    def __init__(self, names: tuple[str, ...], checks: tuple[str, ...]) -> None:
        """Wrap a named list of checks.

        Args:
            names: The rule-set names composed into this one.
            checks: The clang-tidy check globs, in order.
        """
        self._names = names
        self._checks = checks

    @classmethod
    def misra_cpp_2023(cls) -> Rules:
        """Checks approximating MISRA C++:2023 guidance.

        Returns:
            The rule set.
        """
        return cls(
            ("misra_cpp_2023",),
            (
                "bugprone-*",
                "cert-*",
                "cppcoreguidelines-*",
                "hicpp-*",
                "misc-*",
                "-misc-non-private-member-variables-in-classes",
                "readability-braces-around-statements",
                "readability-implicit-bool-conversion",
            ),
        )

    @classmethod
    def autosar(cls) -> Rules:
        """Checks approximating the AUTOSAR C++14 guidelines.

        Returns:
            The rule set.
        """
        return cls(("autosar",), ("cppcoreguidelines-*", "hicpp-*", "modernize-*", "bugprone-*"))

    @classmethod
    def cert(cls) -> Rules:
        """The SEI CERT C and C++ secure coding checks.

        Returns:
            The rule set.
        """
        return cls(("cert",), ("cert-*",))

    @classmethod
    def core_guidelines(cls) -> Rules:
        """The C++ Core Guidelines checks.

        Returns:
            The rule set.
        """
        return cls(("core_guidelines",), ("cppcoreguidelines-*",))

    @classmethod
    def modern(cls) -> Rules:
        """Modernization and readability checks for day-to-day hygiene.

        Returns:
            The rule set.
        """
        return cls(("modern",), ("modernize-*", "readability-*", "performance-*"))

    def __or__(self, other: Rules) -> Rules:
        """Combine two rule sets, keeping first-seen order without duplicates.

        Args:
            other: The rule set to add.

        Returns:
            The combined rule set.
        """
        names = tuple(dict.fromkeys((*self._names, *other._names)))
        checks = tuple(dict.fromkeys((*self._checks, *other._checks)))
        return Rules(names, checks)

    @property
    def checks(self) -> tuple[str, ...]:
        """The clang-tidy check globs this set enables."""
        return self._checks

    def command(self) -> tuple[str, ...]:
        """The clang-tidy command line that runs exactly these checks.

        Returns:
            ("clang-tidy", "-checks=-*,<checks>").
        """
        return ("clang-tidy", f"-checks=-*,{','.join(self._checks)}")

    def __repr__(self) -> str:
        """Developer-facing representation.

        Returns:
            The composed rule-set names.
        """
        return f"Rules({' | '.join(self._names)})"
