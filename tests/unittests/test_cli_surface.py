"""The command-line surface itself: verbs, flags, exit codes, and help.

The behavior of each verb is covered elsewhere; what is pinned here is the
shape of the interface, so a front-end change cannot silently drop a verb,
a short flag, or the usage-error exit code that scripts branch on.
"""

from __future__ import annotations

import pytest

from cmakeless import __version__
from cmakeless.cli import main

SCRIPT_VERBS = (
    "build",
    "configure",
    "test",
    "install",
    "package",
    "clean",
    "lock",
    "options",
    "sbom",
    "vendor",
)
ALL_VERBS = (*SCRIPT_VERBS, "init", "doctor")


def test_help_lists_every_verb(capsys: pytest.CaptureFixture[str]) -> None:
    """Help lists every verb."""
    assert main(["--help"]) == 0
    out = capsys.readouterr().out
    missing = [verb for verb in ALL_VERBS if verb not in out]
    assert not missing, f"top-level help omits verbs: {', '.join(missing)}"


def test_version_prints_the_package_version(capsys: pytest.CaptureFixture[str]) -> None:
    """Version prints the package version."""
    assert main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == f"cmakeless {__version__}"


def test_unknown_verb_is_a_usage_error() -> None:
    """Unknown verb is a usage error."""
    assert main(["definitely-not-a-verb"]) == 2


def test_unknown_flag_is_a_usage_error() -> None:
    """Unknown flag is a usage error."""
    assert main(["build", "--definitely-not-a-flag"]) == 2


def test_no_arguments_is_a_usage_error() -> None:
    """No arguments is a usage error."""
    assert main([]) == 2


@pytest.mark.parametrize("verb", ALL_VERBS)
def test_every_verb_has_its_own_help(verb: str, capsys: pytest.CaptureFixture[str]) -> None:
    """Every verb has its own help."""
    assert main([verb, "--help"]) == 0
    assert f"Usage: cmakeless {verb}" in capsys.readouterr().out


@pytest.mark.parametrize("verb", SCRIPT_VERBS)
def test_every_script_verb_accepts_the_file_flag(
    verb: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Every script verb accepts the file flag."""
    assert main([verb, "--help"]) == 0
    assert "--file" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("verb", "short_flag"),
    [("sbom", "-o"), ("vendor", "-d")],
)
def test_short_flags_survive(
    verb: str, short_flag: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Short flags survive."""
    assert main([verb, "--help"]) == 0
    assert short_flag in capsys.readouterr().out
