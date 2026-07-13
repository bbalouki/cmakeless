# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Benchmark: parallel vs serial dependency resolution.

Resolution is I/O-bound (each package is a network fetch and a hash), so the
one-thread-per-dependency pool overlaps the waits. The GIL is released across
the I/O, so the win shows on standard builds too; a free-threaded interpreter
additionally overlaps the CPU-bound hashing.

Run it under both interpreters to compare:

    python benchmarks/bench_resolution.py
    python3.14t benchmarks/bench_resolution.py
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from cmakeless._parallel import gil_enabled, parallel_map

# Simulated per-package I/O latency (a real fetch is far larger, but a fixed,
# deterministic stand-in keeps the benchmark reproducible).
_LATENCY_SECONDS = 0.05
_PACKAGE_COUNT = 16


def resolve_one(spec: str) -> str:
    """Stand in for resolving one package: an I/O wait, then a result.

    Args:
        spec: The package spec being resolved.

    Returns:
        The spec, unchanged, once the simulated fetch completes.
    """
    time.sleep(_LATENCY_SECONDS)
    return spec


def time_it(label: str, run: object) -> float:
    """Run a zero-argument callable once and report its wall-clock seconds.

    Args:
        label: A name for the console line.
        run: The callable to time.

    Returns:
        The elapsed wall-clock time in seconds.
    """
    start = time.perf_counter()
    run()  # type: ignore[operator]
    elapsed = time.perf_counter() - start
    print(f"  {label:<10} {elapsed:6.3f}s")
    return elapsed


def write_result(
    json_path: Path, version: str, serial: float, parallel: float, speedup: float
) -> None:
    """Write a machine-readable benchmark result as JSON.

    Args:
        json_path: Where to write the result.
        version: The interpreter version string.
        serial: Serial wall-clock seconds.
        parallel: Parallel wall-clock seconds.
        speedup: The serial-to-parallel ratio.
    """
    result = {
        "python_version": version,
        "gil_enabled": gil_enabled(),
        "serial_seconds": serial,
        "parallel_seconds": parallel,
        "speedup": speedup,
    }
    json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")


def main(specs: Sequence[str] | None = None, json_path: Path | None = None) -> None:
    """Time serial and parallel resolution, print the speedup, and optionally write JSON.

    Args:
        specs: The package specs to resolve; None uses a generated set.
        json_path: If given, also write a machine-readable result there.
    """
    generated = [f"pkg{n}/1.0.{n}" for n in range(_PACKAGE_COUNT)]
    packages = list(specs) if specs is not None else generated
    version = ".".join(map(str, sys.version_info[:3]))
    print(f"Python {version}, GIL enabled: {gil_enabled()}")
    print(f"Resolving {len(packages)} packages, {_LATENCY_SECONDS}s simulated latency each:")
    serial = time_it("serial", lambda: [resolve_one(spec) for spec in packages])
    parallel = time_it("parallel", lambda: parallel_map(resolve_one, packages))
    speedup = serial / parallel
    print(f"  speedup    {speedup:6.2f}x")
    if json_path is not None:
        write_result(json_path, version, serial, parallel, speedup)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json", type=Path, default=None, help="Write a machine-readable result to this path."
    )
    main(json_path=parser.parse_args().json)
