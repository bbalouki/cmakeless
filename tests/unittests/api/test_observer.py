# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""The Observer event API: events published for every driver step."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from cmakeless import ConsoleObserver, Project, StepFailed, StepFinished, StepStarted
from cmakeless.driver.cmake_driver import CMakeDriver
from cmakeless.observer import BuildEvent


class Recorder:
    """An observer that records every event it receives."""

    def __init__(self) -> None:
        """Start with an empty event log."""
        self.events: list[BuildEvent] = []

    def on_event(self, event: BuildEvent) -> None:
        """Append the event to the log."""
        self.events.append(event)


class _FakeRun:
    """Returns a scripted subprocess result without running anything."""

    def __init__(self, returncode: int = 0) -> None:
        """Script the exit code every call returns."""
        self._returncode = returncode

    def __call__(self, command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        """Return the scripted completed process."""
        return subprocess.CompletedProcess(args=command, returncode=self._returncode, stdout="")


def _patch(monkeypatch: pytest.MonkeyPatch, returncode: int = 0) -> None:
    """Make cmake discoverable and its subprocess a scripted fake."""
    monkeypatch.setattr("cmakeless.driver.cmake_driver.shutil.which", lambda _: "/usr/bin/cmake")
    monkeypatch.setattr("cmakeless.driver.cmake_driver.subprocess.run", _FakeRun(returncode))


def test_success_publishes_started_then_finished(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Success publishes started then finished."""
    _patch(monkeypatch)
    recorder = Recorder()
    driver = CMakeDriver(source_dir=tmp_path, build_dir=tmp_path / "build", observers=[recorder])
    driver.build()
    assert [type(event).__name__ for event in recorder.events] == ["StepStarted", "StepFinished"]
    assert isinstance(recorder.events[0], StepStarted)
    assert recorder.events[0].step == "build"


def test_failure_publishes_step_failed_with_diagnostics(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Failure publishes step failed with diagnostics."""
    _patch(monkeypatch, returncode=1)
    recorder = Recorder()
    driver = CMakeDriver(source_dir=tmp_path, build_dir=tmp_path / "build", observers=[recorder])
    with pytest.raises(Exception, match="build failed"):
        driver.build()
    assert isinstance(recorder.events[-1], StepFailed)
    assert recorder.events[-1].exit_code == 1


def test_console_observer_prints_the_running_line(capsys: pytest.CaptureFixture[str]) -> None:
    """Console observer prints the running line."""
    ConsoleObserver().on_event(StepStarted(step="configure", command=("cmake", "-S", ".")))
    assert "[cmakeless] Running configure:" in capsys.readouterr().out


def test_console_observer_ignores_non_started_events(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Console observer ignores non started events."""
    ConsoleObserver().on_event(StepFinished(step="build", exit_code=0))
    assert capsys.readouterr().out == ""


def test_add_observer_keeps_the_default_console_observer(project_dir: Path) -> None:
    """Add observer keeps the default console observer."""
    project = Project("demo", root=project_dir)
    recorder = Recorder()
    project.add_observer(recorder)
    assert any(isinstance(observer, ConsoleObserver) for observer in project._observers)
    assert recorder in project._observers
