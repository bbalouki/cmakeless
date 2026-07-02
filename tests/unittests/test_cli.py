"""CLI behavior: finding build.py, running it, and reporting failures."""

from __future__ import annotations

from pathlib import Path

import pytest

from cmakeless.cli import main


def test_missing_build_script_fails_with_guidance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Missing build script fails with guidance."""
    monkeypatch.chdir(tmp_path)
    assert main(["build"]) == 1
    captured = capsys.readouterr()
    assert "build.py" in captured.err
    assert "--file" in captured.err


def test_build_runs_the_script(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Build runs the script."""
    marker = tmp_path / "ran.txt"
    script = tmp_path / "build.py"
    script.write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('yes')\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    assert main(["build"]) == 0
    assert marker.read_text() == "yes"


def test_cmakeless_errors_become_exit_code_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Cmakeless errors become exit code one."""
    script = tmp_path / "build.py"
    script.write_text(
        "from cmakeless.errors import ConfigurationError\n"
        "raise ConfigurationError('bad build description')\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    assert main(["build"]) == 1
    captured = capsys.readouterr()
    assert "bad build description" in captured.err


def test_file_flag_points_at_another_script(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """File flag points at another script."""
    marker = tmp_path / "ran.txt"
    script = tmp_path / "other.py"
    script.write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('yes')\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    assert main(["build", "--file", "other.py"]) == 0
    assert marker.is_file()
