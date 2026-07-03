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

import sys
import time
from collections.abc import Sequence

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


def main(specs: Sequence[str] | None = None) -> None:
    """Time serial and parallel resolution and print the speedup.

    Args:
        specs: The package specs to resolve; None uses a generated set.
    """
    generated = [f"pkg{n}/1.0.{n}" for n in range(_PACKAGE_COUNT)]
    packages = list(specs) if specs is not None else generated
    version = ".".join(map(str, sys.version_info[:3]))
    print(f"Python {version}, GIL enabled: {gil_enabled()}")
    print(f"Resolving {len(packages)} packages, {_LATENCY_SECONDS}s simulated latency each:")
    serial = time_it("serial", lambda: [resolve_one(spec) for spec in packages])
    parallel = time_it("parallel", lambda: parallel_map(resolve_one, packages))
    print(f"  speedup    {serial / parallel:6.2f}x")


if __name__ == "__main__":
    main()
