"""The command-line surface itself: verbs, flags, exit codes, and help.

The behavior of each verb is covered elsewhere; what is pinned here is the
shape of the interface, so a front-end change cannot silently drop a verb,
a short flag, or the usage-error exit code that scripts branch on.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cmakeless import __version__
from cmakeless.cli import main
from cmakeless.driver.doctor import DoctorCheck

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


def test_a_failed_required_check_makes_doctor_exit_one(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A failed required check makes doctor exit one."""
    failing = (
        DoctorCheck(name="cmake", ok=False, required=True, detail="not found on PATH"),
        DoctorCheck(name="ccache", ok=False, required=False, detail="not found on PATH"),
    )
    monkeypatch.setattr("cmakeless.cli.run_diagnostics", lambda: failing)
    assert main(["doctor"]) == 1
    out = capsys.readouterr().out
    assert "cmake" in out
    assert "FAIL" in out
    assert "missing" in out


def test_doctor_exits_zero_when_only_optional_checks_fail(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Doctor exits zero when only optional checks fail."""
    checks = (
        DoctorCheck(name="cmake", ok=True, required=True, detail="3.31.0"),
        DoctorCheck(name="vcpkg", ok=False, required=False, detail="not found on PATH"),
    )
    monkeypatch.setattr("cmakeless.cli.run_diagnostics", lambda: checks)
    assert main(["doctor"]) == 0
    assert "vcpkg" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("directory", "expected"),
    [
        ("9lives", "project_9lives"),
        ("my project", "my_project"),
        ("+plus", "project_+plus"),
    ],
)
def test_init_derives_a_valid_project_name_from_the_directory(
    directory: str, expected: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Init derives a valid project name from the directory."""
    work = tmp_path / directory
    work.mkdir()
    monkeypatch.chdir(work)
    assert main(["init"]) == 0
    assert f'Project("{expected}"' in (work / "cmakelessfile.py").read_text(encoding="utf-8")


class _StubCommand:
    """A command layer stand-in, to pin how main() maps its outcome to a code."""

    def __init__(self, outcome: object) -> None:
        """Record what main() should be told, either a raise or a return."""
        self._outcome = outcome

    def main(self, **_kwargs: object) -> object:
        """Return normally, or exit with the recorded code."""
        if isinstance(self._outcome, SystemExit):
            raise self._outcome
        return self._outcome


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (None, 0),
        (SystemExit(None), 0),
        (SystemExit(0), 0),
        (SystemExit(2), 2),
        (SystemExit("something went wrong"), 1),
    ],
)
def test_main_maps_the_command_outcome_to_an_exit_code(
    outcome: object, expected: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Main maps the command outcome to an exit code.

    Scripts branch on these, so the mapping is pinned here rather than left
    to whatever the command layer happens to do: a normal return and a bare
    exit both mean success, an integer passes through, and a message-style
    exit means failure.
    """
    monkeypatch.setattr("typer.main.get_command", lambda _app: _StubCommand(outcome))
    assert main(["build"]) == expected
