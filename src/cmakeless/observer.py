# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""The Observer event API: stable progress events for third-party consumers.

Like the exception hierarchy in errors.py, this is cross-cutting: the driver
publishes one event per pipeline step to every registered observer, so IDE
extensions, CI log formatters, and the default console display are listeners
rather than special cases inside the driver.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from cmakeless.errors import Diagnostic


@dataclass(frozen=True, slots=True)
class BuildEvent:
    """Base class for every progress event the driver publishes.

    Attributes:
        step: The pipeline step the event belongs to ("configure",
            "build", "test", "install", or "package").
    """

    step: str


@dataclass(frozen=True, slots=True)
class StepStarted(BuildEvent):
    """A pipeline step is about to run its command.

    Attributes:
        command: The exact argument vector being executed.
    """

    command: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class StepFinished(BuildEvent):
    """A pipeline step finished successfully.

    Attributes:
        exit_code: The command's exit code (zero on success).
    """

    exit_code: int = 0


@dataclass(frozen=True, slots=True)
class StepFailed(BuildEvent):
    """A pipeline step exited non-zero.

    Attributes:
        exit_code: The command's non-zero exit code.
        diagnostics: Structured errors parsed from the output, first error
            first; may be empty when nothing recognizable was found.
    """

    exit_code: int = 1
    diagnostics: tuple[Diagnostic, ...] = field(default_factory=tuple)


@runtime_checkable
class Observer(Protocol):
    """A consumer of build progress events.

    Implement on_event to receive every event the driver publishes; register
    an instance with project.add_observer(...).
    """

    def on_event(self, event: BuildEvent) -> None:
        """Handle one build event.

        Args:
            event: The event just published by the driver.
        """
        ...


class ConsoleObserver:
    """The default observer: prints the running-command line to the console.

    Reproduces the historical '[cmakeless] Running <step>: <command>'
    output so the console display is a listener like any other.
    """

    def on_event(self, event: BuildEvent) -> None:
        """Print the command line when a step starts.

        Args:
            event: The event to render; only StepStarted prints.
        """
        if isinstance(event, StepStarted):
            command = subprocess.list2cmdline(list(event.command))
            print(f"[cmakeless] Running {event.step}: {command}")


def publish(observers: Sequence[Observer], event: BuildEvent) -> None:
    """Send one event to every observer in order.

    Args:
        observers: The registered observers.
        event: The event to deliver.
    """
    for observer in observers:
        observer.on_event(event)
