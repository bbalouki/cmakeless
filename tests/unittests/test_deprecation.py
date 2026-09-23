"""The deprecation helpers: warn once, name the replacement, change nothing else."""

from __future__ import annotations

import pytest

from cmakeless import deprecated, warn_deprecated_argument


@deprecated(replacement="new_spelling()", removed_in="2.0.0")
def _old_spelling(value: int, *, double: bool = False) -> int:
    """Return the value, doubled on request."""
    return value * 2 if double else value


def test_calling_a_deprecated_function_warns() -> None:
    """Calling a deprecated function warns."""
    with pytest.warns(DeprecationWarning) as record:
        _old_spelling(1)
    assert len(record) == 1


def test_the_warning_names_the_replacement_and_the_removal_version() -> None:
    """The warning names the replacement and the removal version."""
    with pytest.warns(DeprecationWarning) as record:
        _old_spelling(1)
    message = str(record[0].message)
    assert "new_spelling()" in message
    assert "2.0.0" in message


def test_the_deprecated_function_still_works() -> None:
    """The deprecated function still works."""
    with pytest.warns(DeprecationWarning):
        assert _old_spelling(21, double=True) == 42


def test_metadata_survives_the_decorator() -> None:
    """Metadata survives the decorator."""
    assert _old_spelling.__name__ == "_old_spelling"
    assert _old_spelling.__doc__ is not None
    assert "Return the value, doubled on request." in _old_spelling.__doc__
    assert "deprecated" in _old_spelling.__doc__


def test_a_deprecated_argument_warns_with_its_owner() -> None:
    """A deprecated argument warns with its owner."""
    with pytest.warns(DeprecationWarning) as record:
        warn_deprecated_argument(
            "headers", owner="Project.install()", replacement="public_headers=", removed_in="2.0.0"
        )
    message = str(record[0].message)
    assert "'headers'" in message
    assert "Project.install()" in message
    assert "public_headers=" in message
