"""The free-threaded helpers: GIL detection and ordered parallel mapping."""

from __future__ import annotations

import threading

from cmakeless._parallel import gil_enabled, parallel_map


def test_gil_enabled_returns_a_bool() -> None:
    """Gil enabled returns a bool."""
    assert isinstance(gil_enabled(), bool)


def test_parallel_map_preserves_input_order() -> None:
    """Parallel map preserves input order."""
    assert parallel_map(lambda value: value * value, [1, 2, 3, 4]) == [1, 4, 9, 16]


def test_parallel_map_of_empty_returns_empty() -> None:
    """Parallel map of empty returns empty."""
    assert parallel_map(lambda value: value, []) == []


def test_parallel_map_actually_overlaps_workers() -> None:
    """Parallel map actually overlaps workers."""
    worker_count = 4
    barrier = threading.Barrier(worker_count, timeout=5)

    def wait_for_all(index: int) -> int:
        """Block until every worker arrives, proving they overlap."""
        barrier.wait()
        return index

    assert parallel_map(wait_for_all, list(range(worker_count))) == list(range(worker_count))
