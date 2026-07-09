# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Benchmark: parallel vs serial multi-preset configure.

Configuring several presets means running independent CMake configures, each
into its own build tree, over one shared frozen model. That is exactly the
shape a thread pool speeds up. With CMake on PATH this runs real configures;
without it, it falls back to a clearly labelled simulated workload so the
harness still runs anywhere.

    python benchmarks/bench_presets.py
    python3.14t benchmarks/bench_presets.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from cmakeless import Preset, Project
from cmakeless._parallel import gil_enabled, parallel_map
from cmakeless.deps import DependencyProvider
from cmakeless.model.nodes import ProjectModel

_PRESET_COUNT = 6
_SIMULATED_LATENCY_SECONDS = 0.4
_OPTIMIZE_LEVELS = ("none", "release", "relwithdebinfo", "minsize", "debug")


def _write_project(root: Path) -> tuple[Project, list[str]]:
    """Create a tiny project with several presets on disk.

    Args:
        root: The temporary project root to populate.

    Returns:
        The project and the list of its preset names.
    """
    (root / "src").mkdir()
    (root / "src" / "main.cpp").write_text("auto main() -> int { return 0; }\n", encoding="utf-8")
    project = Project("bench", version="1.0.0", cpp_std=20, root=root)
    project.add_executable("bench", sources=["src/main.cpp"])
    names = [f"cfg{index}" for index in range(_PRESET_COUNT)]
    for index, name in enumerate(names):
        project.add_preset(Preset(name, optimize=_OPTIMIZE_LEVELS[index % len(_OPTIMIZE_LEVELS)]))
    return project, names


def _real_configure(
    project: Project, model: ProjectModel, provider: DependencyProvider | None, name: str
) -> None:
    """Run one real CMake configure for a preset into its own build tree.

    Args:
        project: The project whose preset to configure.
        model: The already-resolved project model, presets included.
        provider: The dependency backend, or None for a dep-free tree.
        name: The preset name.
    """
    project._configure_one(model, provider, name)


def _simulated_configure(name: str) -> None:
    """Stand in for a CMake configure with a fixed subprocess-like wait.

    Args:
        name: The preset name (unused; the wait is uniform).
    """
    del name
    time.sleep(_SIMULATED_LATENCY_SECONDS)


def _time(label: str, run: Callable[[], object]) -> float:
    """Run a callable once and print its wall-clock seconds.

    Args:
        label: The console label.
        run: The callable to time.

    Returns:
        The elapsed seconds.
    """
    start = time.perf_counter()
    run()
    elapsed = time.perf_counter() - start
    print(f"  {label:<10} {elapsed:6.3f}s")
    return elapsed


def _run(
    configure: Callable[[str], None],
    names: Sequence[str],
    reset: Callable[[], None] = lambda: None,
) -> None:
    """Time serial then parallel configuration over the preset names.

    Args:
        configure: The per-preset configure callable.
        names: The preset names to configure.
        reset: Cleanup run before each phase so both do the full work from
            a cold build tree (real configures cache aggressively).
    """
    reset()
    serial = _time("serial", lambda: [configure(name) for name in names])
    reset()
    parallel = _time("parallel", lambda: parallel_map(configure, list(names)))
    print(f"  speedup    {serial / parallel:6.2f}x")


def main() -> None:
    """Detect CMake and benchmark real or simulated multi-preset configure."""
    print(f"Python {'.'.join(map(str, sys.version_info[:3]))}, GIL enabled: {gil_enabled()}")
    if shutil.which("cmake") is None:
        print(f"CMake not found; simulated configure, {_SIMULATED_LATENCY_SECONDS}s each:")
        _run(_simulated_configure, [f"cfg{index}" for index in range(_PRESET_COUNT)])
        return
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        project, names = _write_project(root)
        model = project._resolved_model()
        project._write_outputs(model)
        provider = project._provider(model)
        print(f"Real CMake configure of {len(names)} presets:")
        _run(
            lambda name: _real_configure(project, model, provider, name),
            names,
            reset=lambda: shutil.rmtree(root / "build", ignore_errors=True),
        )


if __name__ == "__main__":
    main()
