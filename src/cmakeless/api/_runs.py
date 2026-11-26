"""Translate the CLI's run options into the driver's step options."""

from __future__ import annotations

from pathlib import Path

from cmakeless.api import _context
from cmakeless.driver.cmake_driver import BuildOptions, TestOptions


def build_options() -> BuildOptions:
    """The target, jobs, configuration, and verbosity for this run.

    Returns:
        The driver's build options.
    """
    options = _context.active_run_options()
    return BuildOptions(
        target=options.target, jobs=options.jobs, config=options.config, verbose=options.verbose
    )


def test_options(*, junit: Path | None = None) -> TestOptions:
    """The test selection, repetition, and JUnit path for this run.

    Args:
        junit: A JUnit path that overrides the CLI's --junit, or None.

    Returns:
        The driver's test options.
    """
    options = _context.active_run_options()
    report = junit
    if report is None and options.junit is not None:
        report = Path(options.junit).resolve()
    return TestOptions(
        filter=options.test_filter,
        label=options.test_label,
        repeat=options.test_repeat,
        junit=report,
    )
